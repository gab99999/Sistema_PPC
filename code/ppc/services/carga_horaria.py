# ppc/services/carga_horaria.py
from ..models import ComponenteNaMatriz, ResumoCargaHorariaPPC

MINIMOS_LICENCIATURA = {1: 880, 2: 1600, 3: 320, 4: 400}
NOMES_GRUPOS_LICENCIATURA = {
    1: "Grupo 1",
    2: "Grupo 2",
    3: "Grupo 3 (ACEx)",
    4: "Grupo 4 (Estágio)",
}


def _horas_sem_acex(componente):
    # ACEx entra só no Grupo 3, para não contar duas vezes
    if componente.tipo == 'atividade':
        return componente.carga_horaria_estudante or 0
    return componente.carga_horaria_teorica + componente.carga_horaria_pratica


def _calcular_grupos_licenciatura(ppc, itens, acex_total):
    if ppc.grau_academico != 'licenciatura':
        return None

    horas = {1: 0, 2: 0, 3: acex_total, 4: 0}
    sem_grupo = 0
    for i in itens:
        if i.grupo_licenciatura in (1, 2, 4):
            horas[i.grupo_licenciatura] += _horas_sem_acex(i.componente)
        else:
            sem_grupo += 1

    grupos = []
    for numero in (1, 2, 3, 4):
        minimo = MINIMOS_LICENCIATURA[numero]
        grupos.append({
            "numero": numero,
            "nome": NOMES_GRUPOS_LICENCIATURA[numero],
            "horas": horas[numero],
            "minimo": minimo,
            "atende": horas[numero] >= minimo,
            "falta": max(minimo - horas[numero], 0),
        })
    return {"grupos": grupos, "sem_grupo": sem_grupo}

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

    acex_total = acex_obrig + acex_optat + acex_nl + acex_extensao
    grupos_licenciatura = _calcular_grupos_licenciatura(ppc, itens, acex_total)

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
        "grupos_licenciatura": grupos_licenciatura,
    }

def sincronizar_carga_horaria_total(ppc):
    """Recalcula o resumo e atualiza ppc.carga_horaria_total se tiver mudado."""
    resumo = calcular_resumo_carga_horaria(ppc)
    if ppc.carga_horaria_total != resumo["total"]:
        ppc.carga_horaria_total = resumo["total"]
        ppc.save(update_fields=["carga_horaria_total"])
    return resumo

