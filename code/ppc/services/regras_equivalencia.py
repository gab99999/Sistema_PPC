"""Regra compartilhada de elegibilidade e sugestão de equivalências."""
import unicodedata

from ppc.models import PPC, MatrizReferenciaCurricular


def normalizar_ementa(valor):
    return unicodedata.normalize("NFC", " ".join(str(valor or "").split()))


def carga_total_segura(componente):
    """Retorna (carga, motivo); atividade sem CH de estudante é dado incompleto."""
    if componente.tipo == "atividade":
        if componente.carga_horaria_estudante is None:
            return None, "Carga horária incompleta: atividade sem carga horária do estudante."
        return componente.carga_horaria_estudante + (componente.carga_horaria_acex or 0), ""
    campos = (componente.carga_horaria_teorica, componente.carga_horaria_pratica)
    if any(valor is None for valor in campos):
        return None, "Carga horária incompleta."
    return sum(campos) + (componente.carga_horaria_acex or 0), ""


def carga_item_segura(item):
    return carga_total_segura(item.componente)


def _cadeia(item, anterior):
    if hasattr(item, "matriz_id"):
        atual, antigo = item.matriz, anterior.matriz
        if atual.pk == antigo.pk:
            return False, "A equivalência precisa ligar matrizes diferentes."
        if not atual.curso_id or atual.curso_id != antigo.curso_id:
            return False, "As matrizes precisam estar vinculadas ao mesmo curso."
        vistos, cursor = {atual.pk}, atual.matriz_anterior_id
        while cursor:
            if cursor in vistos:
                return False, "A linhagem da matriz contém um ciclo."
            vistos.add(cursor)
            if cursor == antigo.pk:
                return True, ""
            cursor = MatrizReferenciaCurricular.objects.filter(pk=cursor).values_list("matriz_anterior_id", flat=True).first()
        return False, "A matriz anterior não está na linhagem de edições anteriores."
    atual, antigo = item.ppc, anterior.ppc
    if atual.pk == antigo.pk:
        return False, "A equivalência precisa ligar PPCs diferentes."
    if not atual.curso_id or atual.curso_id != antigo.curso_id:
        return False, "Os PPCs precisam pertencer ao mesmo curso."
    vistos, cursor = {atual.pk}, atual.ppc_anterior_id
    while cursor:
        if cursor in vistos:
            return False, "A linhagem do PPC contém um ciclo."
        vistos.add(cursor)
        if cursor == antigo.pk:
            return True, ""
        cursor = PPC.objects.filter(pk=cursor).values_list("ppc_anterior_id", flat=True).first()
    return False, "O PPC anterior não está na cadeia de edições anteriores."


def avaliar_equivalencia(anterior, nova):
    """Elegibilidade: cadeia/curso + CH total + ACEx. Ementa só sugere automaticamente."""
    comp_ant, comp_nova = anterior.componente, nova.componente
    elegivel, motivo_cadeia = _cadeia(nova, anterior)
    ch_ant, erro_ant = carga_item_segura(anterior)
    ch_nova, erro_nova = carga_item_segura(nova)
    motivos = []
    if not elegivel:
        motivos.append(motivo_cadeia)
    if erro_ant or erro_nova:
        motivos.append(erro_ant or erro_nova)
    elif ch_ant < ch_nova:
        motivos.append(f"CH total insuficiente: anterior {ch_ant} h, nova {ch_nova} h.")
    acex_ant = comp_ant.carga_horaria_acex or 0
    acex_nova = comp_nova.carga_horaria_acex or 0
    if acex_ant < acex_nova:
        motivos.append(f"ACEx insuficiente: anterior {acex_ant} h, nova {acex_nova} h.")
    mesma_ementa = bool(normalizar_ementa(comp_nova.ementa) and normalizar_ementa(comp_nova.ementa) == normalizar_ementa(comp_ant.ementa))
    return {
        "elegivel": not motivos, "motivos": motivos,
        "carga_anterior": ch_ant, "carga_nova": ch_nova,
        "acex_anterior": acex_ant, "acex_nova": acex_nova,
        "sugestao_automatica": not motivos and mesma_ementa,
    }
