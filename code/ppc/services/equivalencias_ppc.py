"""Equivalências específicas entre os vínculos curriculares de PPCs sucessivos."""
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from ppc.models import PPC, ComponenteNaMatriz, EquivalenciaPPC
from ppc.services.equivalencias_matrizes import carga_equivalencia, normalizar_ementa_equivalencia
from ppc.services.regras_equivalencia import avaliar_equivalencia
from ppc.services.eventos import registrar_evento, suspender_eventos_edicao


def cadeia_ppc(ppc):
    if not ppc.curso_id:
        return [], "Vincule este PPC a um curso antes de consultar equivalências."
    anteriores, vistos, cursor = [], {ppc.pk}, ppc.ppc_anterior_id
    while cursor:
        if cursor in vistos:
            return [], "A linhagem deste PPC contém um ciclo e precisa ser corrigida."
        vistos.add(cursor)
        anterior = PPC.objects.filter(pk=cursor).first()
        if not anterior or anterior.curso_id != ppc.curso_id:
            return [], "Um PPC anterior da linhagem não pertence ao mesmo curso."
        anteriores.append(anterior)
        cursor = anterior.ppc_anterior_id
    return anteriores, "" if anteriores else "Selecione o PPC anterior para habilitar as equivalências."


def preparar_editor_ppc(ppc):
    anteriores, erro = cadeia_ppc(ppc)
    if erro: return {"ppc": ppc, "erro": erro, "matrizes_anteriores": [], "linhas": [], "pares_iniciais": [], "automaticas": []}
    novos = list(ppc.matriz_componentes.select_related("componente").order_by("periodo", "componente__nome", "pk"))
    antigos = list(ComponenteNaMatriz.objects.filter(ppc_id__in=[p.pk for p in anteriores]).select_related("componente", "ppc"))
    por_id = {i.pk: i for i in antigos}
    salvas = set(EquivalenciaPPC.objects.filter(item_novo__ppc=ppc).values_list("item_novo_id", "item_anterior_id"))
    auto, linhas = [], []
    for novo in novos:
        chn = carga_equivalencia(novo)
        celulas = []
        for anterior_ppc in anteriores:
            matches, sug_ids = [], []
            for antigo in (item for item in antigos if item.ppc_id == anterior_ppc.pk):
                cha = carga_equivalencia(antigo)
                same = avaliar_equivalencia(antigo, novo)["sugestao_automatica"]
                if same:
                    auto.append([novo.pk, antigo.ppc_id, antigo.pk]); sug_ids.append(str(antigo.pk))
                if (novo.pk, antigo.pk) in salvas:
                    matches.append({"item": antigo, "carga": cha, "automatica": same})
            celulas.append({"matriz": anterior_ppc, "selecionados": matches, "sugestoes": len(sug_ids), "sugestao_ids": ",".join(sug_ids), "sugestoes_pendentes": any((novo.pk, int(i)) not in salvas for i in sug_ids)})
        linhas.append({"item": novo, "carga": chn, "matrizes": celulas})
    pairs = [[n, por_id[a].ppc_id, a] for n, a in salvas if a in por_id]
    legadas_invalidas = []
    for par in EquivalenciaPPC.objects.filter(item_novo__ppc=ppc).select_related(
        "item_novo__componente", "item_novo__ppc", "item_anterior__componente", "item_anterior__ppc"
    ):
        regra = avaliar_equivalencia(par.item_anterior, par.item_novo)
        if not regra["elegivel"]:
            legadas_invalidas.append({"par": par, "motivo": "; ".join(regra["motivos"]), "regra": regra})
    return {"ppc": ppc, "erro": "", "matrizes_anteriores": anteriores, "linhas": linhas,
            "pares_iniciais": pairs, "automaticas": auto, "legadas_invalidas": legadas_invalidas}


def candidatos_ppc(ppc, novo_id, anterior_id, termo="", offset=0, limite=50):
    anteriores, erro = cadeia_ppc(ppc)
    if erro: raise ValidationError(erro)
    if anterior_id not in {p.pk for p in anteriores}: raise ValidationError("O PPC não está na linhagem anterior desta edição.")
    novo = ppc.matriz_componentes.select_related("componente").filter(pk=novo_id).first()
    if not novo: raise ValidationError("Componente não encontrado no PPC atual.")
    qs = ComponenteNaMatriz.objects.filter(ppc_id=anterior_id).select_related("componente")
    if termo: qs = qs.filter(Q(componente__nome__icontains=termo) | Q(componente__codigo__icontains=termo))
    total=qs.count(); itens=list(qs.order_by("componente__nome", "pk")[offset:offset+limite+1]); mais=len(itens)>limite; itens=itens[:limite]
    chn=carga_equivalencia(novo); selected=set(EquivalenciaPPC.objects.filter(item_novo=novo).values_list("item_anterior_id",flat=True))
    out=[]
    for item in itens:
        cha=carga_equivalencia(item); regra=avaliar_equivalencia(item, novo)
        out.append({"id":item.pk,"codigo":item.componente.codigo or "","nome":item.componente.nome,"periodo":item.periodo,"carga":cha,"acex":regra["acex_anterior"],"acex_nova":regra["acex_nova"],"ementa":item.componente.ementa or "","elegivel":regra["elegivel"],"motivo":"; ".join(regra["motivos"]),"motivos_por_condicao":regra["motivos_por_condicao"],"automatica":regra["sugestao_automatica"],"selecionada":item.pk in selected})
    return {"candidatos":out,"total":total,"mais":mais,"proximo_offset":offset+limite}


def salvar_ppc(ppc_id, pares, usuario):
    with transaction.atomic(), suspender_eventos_edicao():
        ppc=PPC.objects.select_for_update().get(pk=ppc_id); anteriores, erro=cadeia_ppc(ppc)
        if erro: raise ValidationError(erro)
        qs=ComponenteNaMatriz.objects.filter(ppc_id__in=[p.pk for p in anteriores]).select_related("componente","ppc")
        antigos={x.pk:x for x in qs}; novos={x.pk:x for x in ppc.matriz_componentes.select_related("componente")}
        chosen=set()
        for n,a in pares:
            novo,antigo=novos.get(int(n)),antigos.get(int(a))
            if not novo or not antigo or antigo.ppc_id not in {p.pk for p in anteriores}: raise ValidationError("Equivalência fora da linhagem de PPCs anteriores.")
            regra=avaliar_equivalencia(antigo, novo)
            if not regra["elegivel"]:
                if EquivalenciaPPC.objects.filter(item_novo=novo, item_anterior=antigo).exists():
                    continue
                raise ValidationError(regra["motivos"])
            chosen.add((novo.pk,antigo.pk))
        existing={(e.item_novo_id,e.item_anterior_id):e for e in EquivalenciaPPC.objects.filter(item_novo__ppc=ppc)}
        invalid_existing={k for k,e in existing.items() if not avaliar_equivalencia(e.item_anterior, e.item_novo)["elegivel"]}
        for k,e in existing.items():
            if k not in chosen and k not in invalid_existing: e.delete()
        for n,a in chosen-existing.keys(): EquivalenciaPPC(item_novo_id=n,item_anterior_id=a,criado_por=usuario).save()
    registrar_evento("equivalencias_ppc_salvas",usuario=usuario,ppc=ppc,identificador=str(ppc.pk),pares=len(chosen))
    return {"salvas":len(chosen)}
