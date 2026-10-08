# ppc/services/carga_horaria.py
from ..models import ComponenteNaMatriz, ResumoCargaHorariaPPC

def calcular_resumo_carga_horaria(ppc):
    itens = ppc.matriz_componentes.select_related("componente").filter(
        componente__status='aprovado'
    )
    nc = sum(i.componente.carga_horaria_computada_total for i in itens if i.nucleo == "NC")
    ne_obrig = sum(i.componente.carga_horaria_computada_total for i in itens
                   if i.nucleo == "NE" and i.natureza == "obrigatoria")
    ne_optat = sum(i.componente.carga_horaria_computada_total for i in itens
                   if i.nucleo == "NE" and i.natureza == "optativa")
    seminario = sum(i.componente.carga_horaria_computada_total for i in itens
                     if i.componente.tipo == "seminario")
    acex_obrig = sum(i.componente.carga_horaria_acex or 0 for i in itens if i.natureza == "obrigatoria")
    acex_optat = sum(i.componente.carga_horaria_acex or 0 for i in itens if i.natureza == "optativa")

    manual = ResumoCargaHorariaPPC.objects.filter(ppc=ppc).first()
    nl = manual.nucleo_livre_manual if manual else 0
    acex_nl = manual.acex_nucleo_livre_manual if manual else 0
    acex_extensao = manual.acex_extensao_manual if manual else 0
    ac = manual.atividades_complementares_manual if manual else 0

    total = nc + ne_obrig + ne_optat + nl + acex_obrig + acex_optat + acex_nl + acex_extensao + ac

    def pct(valor):
        return round((valor / total) * 100, 1) if total else 0

    return {
        "nc": {"ch": nc, "pct": pct(nc)},
        "ne_obrig": {"ch": ne_obrig, "pct": pct(ne_obrig)},
        "ne_optat": {"ch": ne_optat, "pct": pct(ne_optat)},
        "nl": {"ch": nl, "pct": pct(nl)},
        "seminario": {"ch": seminario, "pct": pct(seminario)},
        "acex_obrig": {"ch": acex_obrig, "pct": pct(acex_obrig)},
        "acex_optat": {"ch": acex_optat, "pct": pct(acex_optat)},
        "acex_nl": {"ch": acex_nl, "pct": pct(acex_nl)},
        "acex_extensao": {"ch": acex_extensao, "pct": pct(acex_extensao)},
        "ac": {"ch": ac, "pct": pct(ac)},
        "total": total,
    }

def sincronizar_carga_horaria_total(ppc):
    """Recalcula o resumo e atualiza ppc.carga_horaria_total se tiver mudado."""
    resumo = calcular_resumo_carga_horaria(ppc)
    if ppc.carga_horaria_total != resumo["total"]:
        ppc.carga_horaria_total = resumo["total"]
        ppc.save(update_fields=["carga_horaria_total"])
    return resumo