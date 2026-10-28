"""Equivalências específicas entre os vínculos curriculares de PPCs sucessivos."""
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from ppc.models import PPC, ComponenteNaMatriz, EquivalenciaPPC
from ppc.services.equivalencias_matrizes import carga_equivalencia, normalizar_ementa_equivalencia
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
                same = bool(chn is not None and cha is not None and cha >= chn and normalizar_ementa_equivalencia(novo.componente.ementa) and normalizar_ementa_equivalencia(novo.componente.ementa) == normalizar_ementa_equivalencia(antigo.componente.ementa))
                if same:
                    auto.append([novo.pk, antigo.ppc_id, antigo.pk]); sug_ids.append(str(antigo.pk))
                if (novo.pk, antigo.pk) in salvas:
                    matches.append({"item": antigo, "carga": cha, "automatica": same})
            celulas.append({"matriz": anterior_ppc, "selecionados": matches, "sugestoes": len(sug_ids), "sugestao_ids": ",".join(sug_ids), "sugestoes_pendentes": any((novo.pk, int(i)) not in salvas for i in sug_ids)})
        linhas.append({"item": novo, "carga": chn, "matrizes": celulas})
    pairs = [[n, por_id[a].ppc_id, a] for n, a in salvas if a in por_id]
    return {"ppc": ppc, "erro": "", "matrizes_anteriores": anteriores, "linhas": linhas, "pares_iniciais": pairs, "automaticas": auto}


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
        cha=carga_equivalencia(item); eleg=chn is not None and cha is not None and cha>=chn
        out.append({"id":item.pk,"codigo":item.componente.codigo or "","nome":item.componente.nome,"periodo":item.periodo,"carga":cha,"ementa":item.componente.ementa or "","elegivel":eleg,"motivo":"" if eleg else ("Carga horária inválida." if cha is None or chn is None else f"CH anterior ({cha} h) menor que a CH nova ({chn} h)."),"automatica":bool(eleg and normalizar_ementa_equivalencia(item.componente.ementa) and normalizar_ementa_equivalencia(item.componente.ementa)==normalizar_ementa_equivalencia(novo.componente.ementa)),"selecionada":item.pk in selected})
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
            chn,cha=carga_equivalencia(novo),carga_equivalencia(antigo)
            if chn is None or cha is None or cha<chn: raise ValidationError("A CH do PPC anterior deve ser igual ou superior à CH do PPC novo.")
            chosen.add((novo.pk,antigo.pk))
        existing={(e.item_novo_id,e.item_anterior_id):e for e in EquivalenciaPPC.objects.filter(item_novo__ppc=ppc)}
        for k,e in existing.items():
            if k not in chosen: e.delete()
        for n,a in chosen-existing.keys(): EquivalenciaPPC(item_novo_id=n,item_anterior_id=a,criado_por=usuario).save()
    registrar_evento("equivalencias_ppc_salvas",usuario=usuario,ppc=ppc,identificador=str(ppc.pk),pares=len(chosen))
    return {"salvas":len(chosen)}
