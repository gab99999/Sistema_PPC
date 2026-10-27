"""Sugestões e validação das equivalências entre edições de uma matriz."""

import unicodedata

from django.core.exceptions import ValidationError
from django.db import transaction

from ppc.models import ComponenteNaMatrizReferencia, EquivalenciaMatriz, MatrizReferenciaCurricular
from ppc.services.eventos import registrar_evento, suspender_eventos_edicao


def normalizar_ementa_equivalencia(valor):
    """Mesma regra do Apps Script: trim, espaços colapsados e Unicode NFC."""
    return unicodedata.normalize("NFC", " ".join(str(valor or "").split()))


def obter_matrizes_anteriores(matriz):
    """Segue a linhagem explícita, sem inferir predecessoras pelo nome."""
    if not matriz.curso_id:
        return [], "Vincule esta matriz a um curso antes de consultar equivalências."

    anteriores = []
    vistos = {matriz.pk}
    cursor_id = matriz.matriz_anterior_id
    while cursor_id:
        if cursor_id in vistos:
            return [], "A linhagem desta matriz contém um ciclo e precisa ser corrigida."
        vistos.add(cursor_id)
        anterior = MatrizReferenciaCurricular.objects.filter(pk=cursor_id).first()
        if anterior is None:
            return [], "Uma matriz anterior da linhagem não foi encontrada."
        if anterior.curso_id != matriz.curso_id:
            return [], "A matriz anterior não pertence ao mesmo curso."
        anteriores.append(anterior)
        cursor_id = anterior.matriz_anterior_id
    return anteriores, ""


def carga_equivalencia(item):
    """A CH vem do cálculo do componente, inclusive a regra de atividades."""
    try:
        return item.componente.carga_horaria_computada_total
    except (TypeError, ValueError):
        # Dados legados incompletos não devem derrubar a tela; ficam inelegíveis
        # para comparação automática até serem corrigidos.
        return None


def consultar_equivalencias_matriz(matriz):
    anteriores, erro = obter_matrizes_anteriores(matriz)
    if erro:
        return {"matriz": matriz, "erro": erro, "matrizes_anteriores": [], "linhas": []}

    itens_novos = list(matriz.componentes.select_related("componente").order_by("periodo", "ordem", "pk"))
    ids_anteriores = [m.pk for m in anteriores]
    itens_anteriores = list(ComponenteNaMatrizReferencia.objects.filter(
        matriz_id__in=ids_anteriores, matriz__curso_id=matriz.curso_id,
    ).select_related("matriz", "componente").order_by("matriz_id", "periodo", "ordem", "pk"))
    salvas = set(EquivalenciaMatriz.objects.filter(
        item_novo__matriz=matriz, item_anterior__matriz_id__in=ids_anteriores,
    ).values_list("item_novo_id", "item_anterior_id"))

    celulas = []
    automaticas = set()
    for novo in itens_novos:
        ch_nova = carga_equivalencia(novo)
        ementa_nova = normalizar_ementa_equivalencia(novo.componente.ementa)
        por_matriz = []
        for anterior in anteriores:
            candidatos = []
            for item_anterior in itens_anteriores:
                if item_anterior.matriz_id != anterior.pk:
                    continue
                ch_anterior = carga_equivalencia(item_anterior)
                if ch_anterior is None or ch_nova is None or ch_anterior < ch_nova:
                    continue
                par = (novo.pk, item_anterior.pk)
                ementa_anterior = normalizar_ementa_equivalencia(item_anterior.componente.ementa)
                auto = bool(ementa_nova and ementa_anterior and ementa_nova == ementa_anterior)
                if auto:
                    automaticas.add(par)
                candidatos.append({
                    "item": item_anterior, "carga": ch_anterior,
                    "automatica": auto, "selecionada": par in salvas or auto,
                })
            por_matriz.append({"matriz": anterior, "candidatos": candidatos})
        celulas.append({"item": novo, "carga": ch_nova, "matrizes": por_matriz})

    return {
        "matriz": matriz, "erro": "", "matrizes_anteriores": anteriores,
        "linhas": celulas, "total_sugestoes": len(automaticas),
    }


def preparar_editor_equivalencias(matriz):
    """Dados compactos para a tabela; nenhum candidato é enviado ao HTML."""
    anteriores, erro = obter_matrizes_anteriores(matriz)
    if erro:
        return {"matriz": matriz, "erro": erro, "matrizes_anteriores": [], "linhas": [], "pares_iniciais": [], "automaticas": []}
    novos = list(matriz.componentes.select_related("componente").order_by("periodo", "componente__nome", "pk"))
    itens_antigos = list(ComponenteNaMatrizReferencia.objects.filter(
        matriz_id__in=[m.pk for m in anteriores], matriz__curso_id=matriz.curso_id,
    ).select_related("componente", "matriz").order_by("matriz_id", "pk"))
    salvas = list(EquivalenciaMatriz.objects.filter(item_novo__matriz=matriz).values_list("item_novo_id", "item_anterior_id"))
    salvas_set = set(salvas)
    antigos_por_id = {i.pk: i for i in itens_antigos}
    antigas_por_matriz = {m.pk: [i for i in itens_antigos if i.matriz_id == m.pk] for m in anteriores}
    linhas, automaticas = [], []
    for novo in novos:
        ch_nova = carga_equivalencia(novo)
        ementa_nova = normalizar_ementa_equivalencia(novo.componente.ementa)
        celulas = []
        for anterior in anteriores:
            selecionados = [i for i in antigas_por_matriz[anterior.pk] if (novo.pk, i.pk) in salvas_set]
            sugestoes = [i for i in antigas_por_matriz[anterior.pk]
                         if ch_nova is not None and carga_equivalencia(i) is not None
                         and ch_nova <= carga_equivalencia(i) and ementa_nova
                         and ementa_nova == normalizar_ementa_equivalencia(i.componente.ementa)]
            sugestao_ids = {i.pk for i in sugestoes}
            automaticas.extend((novo.pk, anterior.pk, i.pk) for i in sugestoes)
            celulas.append({"matriz": anterior, "selecionados": [
                                {"item": i, "carga": carga_equivalencia(i), "automatica": i.pk in sugestao_ids}
                                for i in selecionados
                            ], "sugestoes": len(sugestoes),
                            "sugestao_ids": ",".join(str(i.pk) for i in sugestoes), "sugestoes_ids_set": sugestao_ids,
                            "sugestoes_pendentes": any((novo.pk, i.pk) not in salvas_set for i in sugestoes)})
        linhas.append({"item": novo, "carga": ch_nova, "matrizes": celulas})
    pares_iniciais = [[n, antigos_por_id[a].matriz_id, a] if a in antigos_por_id else [n, 0, a] for n, a in salvas]
    return {"matriz": matriz, "erro": "", "matrizes_anteriores": anteriores,
            "linhas": linhas, "pares_iniciais": pares_iniciais, "automaticas": [list(p) for p in automaticas]}


def candidatos_equivalencia_celula(matriz, item_novo_id, matriz_anterior_id, termo="", offset=0, limite=50):
    """Lista paginada e filtrada para uma única célula, incluindo inelegíveis."""
    anteriores, erro = obter_matrizes_anteriores(matriz)
    if erro:
        raise ValidationError(erro)
    if matriz_anterior_id not in {m.pk for m in anteriores}:
        raise ValidationError("A matriz selecionada não está na linhagem anterior desta edição.")
    novo = matriz.componentes.select_related("componente").filter(pk=item_novo_id).first()
    if not novo:
        raise ValidationError("O componente da matriz nova não foi encontrado.")
    qs = ComponenteNaMatrizReferencia.objects.filter(
        matriz_id=matriz_anterior_id, matriz__curso_id=matriz.curso_id,
    ).select_related("componente", "matriz")
    termo = (termo or "").strip()
    if termo:
        from django.db.models import Q
        qs = qs.filter(Q(componente__nome__icontains=termo) | Q(componente__codigo__icontains=termo))
    total = qs.count()
    candidatos = list(qs.order_by("componente__nome", "pk")[offset:offset + limite + 1])
    mais = len(candidatos) > limite
    candidatos = candidatos[:limite]
    ch_nova = carga_equivalencia(novo)
    ementa_nova = normalizar_ementa_equivalencia(novo.componente.ementa)
    salvas = set(EquivalenciaMatriz.objects.filter(item_novo=novo).values_list("item_anterior_id", flat=True))
    resultado = []
    for item in candidatos:
        ch = carga_equivalencia(item)
        ementa = normalizar_ementa_equivalencia(item.componente.ementa)
        resultado.append({
            "id": item.pk, "codigo": item.componente.codigo or "", "nome": item.componente.nome,
            "periodo": item.periodo, "carga": ch, "ementa": item.componente.ementa or "", "matriz_id": item.matriz_id,
            "elegivel": ch is not None and ch_nova is not None and ch >= ch_nova,
            "motivo": ("Carga horária inválida nos dados do componente." if ch is None or ch_nova is None
                       else "" if ch >= ch_nova else f"CH anterior ({ch} h) menor que a CH nova ({ch_nova} h)."),
            "automatica": bool(ch is not None and ch_nova is not None and ch >= ch_nova and ementa_nova and ementa and ementa_nova == ementa),
            "selecionada": item.pk in salvas,
        })
    return {"candidatos": resultado, "total": total, "mais": mais, "proximo_offset": offset + limite}


def previsualizar_equivalencias_matriz(matriz, pares):
    """Valida a seleção não salva e devolve linhas aceitas e pares rejeitados."""
    anteriores, erro = obter_matrizes_anteriores(matriz)
    if erro:
        return {"erro": erro, "linhas": [], "rejeitados": [], "com": 0, "sem": 0}
    ids_anteriores = {m.pk for m in anteriores}
    novos = {i.pk: i for i in matriz.componentes.select_related("componente").all()}
    antigos = {i.pk: i for i in ComponenteNaMatrizReferencia.objects.filter(
        matriz_id__in=ids_anteriores, matriz__curso_id=matriz.curso_id,
    ).select_related("matriz", "componente")}
    try:
        ids_enviados = {int(par[1]) for par in pares if isinstance(par, (list, tuple)) and len(par) > 1}
    except (TypeError, ValueError):
        ids_enviados = set()
    antigos_enviados = {i.pk: i for i in ComponenteNaMatrizReferencia.objects.filter(
        pk__in=ids_enviados,
    ).select_related("matriz", "componente")}
    aceitos, rejeitados = set(), []
    for par in pares:
        try:
            novo_id, antigo_id = int(par[0]), int(par[1])
        except (TypeError, ValueError, IndexError):
            rejeitados.append({"par": str(par), "motivo": "Formato de par inválido."})
            continue
        novo, antigo = novos.get(novo_id), antigos_enviados.get(antigo_id)
        motivo = ""
        if novo is None:
            motivo = "Componente não encontrado na matriz nova."
        elif antigo is None:
            motivo = "Componente da matriz anterior não encontrado."
        elif antigo.matriz.curso_id != matriz.curso_id:
            motivo = "A matriz do componente anterior não pertence ao mesmo curso."
        elif antigo.matriz_id not in ids_anteriores:
            motivo = "A matriz do componente não está na cadeia de edições anteriores."
        elif carga_equivalencia(antigo) is None or carga_equivalencia(novo) is None:
            motivo = "Carga horária inválida nos dados do componente."
        elif carga_equivalencia(antigo) < carga_equivalencia(novo):
            motivo = f"CH anterior ({carga_equivalencia(antigo)} h) menor que a CH nova ({carga_equivalencia(novo)} h)."
        if motivo:
            rejeitados.append({"par": f"{novo_id} → {antigo_id}", "motivo": motivo})
        else:
            aceitos.add((novo_id, antigo_id))
    linhas = []
    for item in sorted(novos.values(), key=lambda i: (i.periodo, i.componente.nome or "")):
        equivalentes = []
        for novo_id, antigo_id in aceitos:
            if novo_id == item.pk:
                antigo = antigos[antigo_id]
                equivalentes.append({"matriz": antigo.matriz, "item": antigo})
        celulas = [{"matriz": anterior, "equivalentes": [eq for eq in equivalentes if eq["matriz"].pk == anterior.pk]}
                   for anterior in anteriores]
        linhas.append({"item": item, "carga_total": carga_equivalencia(item), "equivalentes": equivalentes, "celulas": celulas})
        for eq in equivalentes:
            eq["carga_total"] = carga_equivalencia(eq["item"])
    com = sum(bool(row["equivalentes"]) for row in linhas)
    pares_automaticos = set()
    for novo in novos.values():
        ch_nova = carga_equivalencia(novo)
        ementa_nova = normalizar_ementa_equivalencia(novo.componente.ementa)
        if ch_nova is None or not ementa_nova:
            continue
        for antigo in antigos.values():
            ch_antiga = carga_equivalencia(antigo)
            ementa_antiga = normalizar_ementa_equivalencia(antigo.componente.ementa)
            if ch_antiga is not None and ch_antiga >= ch_nova and ementa_antiga == ementa_nova:
                pares_automaticos.add((novo.pk, antigo.pk))
    automaticas = manuais = pendentes = 0
    por_novo = {}
    for novo_id, antigo_id in aceitos:
        por_novo.setdefault(novo_id, []).append((novo_id, antigo_id))
    for novo in novos.values():
        pares_novo = por_novo.get(novo.pk, [])
        if not pares_novo:
            pendentes += 1
        elif all(par in pares_automaticos for par in pares_novo):
            automaticas += 1
        else:
            manuais += 1
    return {"matriz": matriz, "erro": "", "linhas": linhas, "rejeitados": rejeitados, "com": com,
            "sem": len(linhas) - com, "total_rejeitados": len(rejeitados),
            "matrizes_anteriores": anteriores, "automaticas": automaticas,
            "manuais": manuais, "pendentes": pendentes}


def salvar_equivalencias_matriz(matriz_id, pares_enviados, usuario):
    """Recalcula candidatos sob bloqueio transacional e salva apenas pares válidos."""
    resumo = {"adicionadas": 0, "removidas": 0, "mantidas": 0}
    with transaction.atomic(), suspender_eventos_edicao():
        matriz = MatrizReferenciaCurricular.objects.select_for_update().get(pk=matriz_id)
        dados = consultar_equivalencias_matriz(matriz)
        if dados["erro"]:
            raise ValidationError(dados["erro"])

        permitidos = {
            (linha["item"].pk, candidato["item"].pk)
            for linha in dados["linhas"]
            for celula in linha["matrizes"]
            for candidato in celula["candidatos"]
        }
        selecionados = set(pares_enviados)
        if not selecionados.issubset(permitidos):
            raise ValidationError("Uma ou mais equivalências não são válidas para a linhagem e a CH atuais.")

        existentes = {
            (par.item_novo_id, par.item_anterior_id): par
            for par in EquivalenciaMatriz.objects.filter(item_novo__matriz=matriz)
        }
        for chave, par in existentes.items():
            if chave in selecionados:
                resumo["mantidas"] += 1
            else:
                par.delete()
                resumo["removidas"] += 1
        for novo_id, anterior_id in selecionados - existentes.keys():
            par = EquivalenciaMatriz(
                item_novo_id=novo_id, item_anterior_id=anterior_id,
                criado_por=usuario,
            )
            par._change_reason = "Equivalências da matriz salvas pela interface"
            par.save()
            resumo["adicionadas"] += 1

    registrar_evento(
        "equivalencias_matriz_salvas", usuario=usuario, curso=matriz.curso,
        identificador=str(matriz.pk), **resumo,
    )
    return resumo
