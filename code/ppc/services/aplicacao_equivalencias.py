"""Copia equivalências da matriz de referência para os vínculos de um PPC."""
from ppc.models import ComponenteNaMatriz, EquivalenciaMatriz, EquivalenciaPPC
from ppc.services.equivalencias_ppc import cadeia_ppc
from ppc.services.regras_equivalencia import avaliar_equivalencia


def traduzir_equivalencias_matriz_para_ppc(
    matriz, ppc, *, usuario=None, aplicar=False, componentes_planejados=None,
):
    """Classifica e, opcionalmente, cria cópias dos pares que têm destino inequívoco."""
    resultado = {"criadas": [], "existentes": [], "nao_aplicaveis": []}
    planejados = set(componentes_planejados or ())
    pares = EquivalenciaMatriz.objects.filter(item_novo__matriz=matriz).select_related(
        "item_novo__componente", "item_anterior__componente",
        "item_novo__matriz", "item_anterior__matriz",
    ).order_by("item_novo_id", "item_anterior_id")
    if not pares.exists():
        return resultado

    anteriores, erro_cadeia = cadeia_ppc(ppc) if ppc.ppc_anterior_id else ([], "PPC sem ppc_anterior.")
    ids_anteriores = [item.pk for item in anteriores]
    atuais = {
        item.componente_id: item
        for item in ComponenteNaMatriz.objects.filter(ppc=ppc).select_related("componente", "ppc")
    }

    def nao_aplicavel(par, motivo):
        resultado["nao_aplicaveis"].append({
            "par": par, "item_novo": par.item_novo,
            "item_anterior": par.item_anterior, "motivo": motivo,
        })

    for par in pares:
        item_novo, item_anterior = par.item_novo, par.item_anterior
        comp_novo, comp_anterior = item_novo.componente, item_anterior.componente

        if not matriz.curso_id:
            nao_aplicavel(par, "matriz sem curso")
            continue
        if not ppc.curso_id or matriz.curso_id != ppc.curso_id:
            nao_aplicavel(par, "matriz e PPC não pertencem ao mesmo curso")
            continue
        if not ppc.ppc_anterior_id:
            nao_aplicavel(par, "PPC sem ppc_anterior")
            continue
        if erro_cadeia:
            nao_aplicavel(par, erro_cadeia)
            continue
        if comp_novo.status != "aprovado" or comp_anterior.status != "aprovado":
            nao_aplicavel(par, "componente aguardando aprovação")
            continue

        novo_ppc = atuais.get(comp_novo.pk)
        if novo_ppc is None and item_novo.pk in planejados:
            novo_ppc = ComponenteNaMatriz(
                ppc=ppc, componente=comp_novo, periodo=item_novo.periodo,
                natureza=item_novo.natureza, nucleo=item_novo.nucleo,
                grupo_licenciatura=item_novo.grupo_licenciatura,
            )
        if novo_ppc is None:
            nao_aplicavel(par, "componente novo não existe no PPC atual")
            continue

        candidatos = list(ComponenteNaMatriz.objects.filter(
            ppc_id__in=ids_anteriores, componente_id=comp_anterior.pk,
        ).select_related("componente", "ppc").order_by("ppc_id", "pk"))
        if not candidatos:
            nao_aplicavel(par, "componente anterior não está na cadeia de PPCs anteriores")
            continue
        if len(candidatos) > 1:
            nao_aplicavel(par, "mais de um vínculo candidato na cadeia de PPCs anteriores (ambiguidade)")
            continue
        anterior_ppc = candidatos[0]

        regra = avaliar_equivalencia(anterior_ppc, novo_ppc)
        if not regra["elegivel"]:
            nao_aplicavel(par, "; ".join(regra["motivos"]))
            continue

        existente = None
        if novo_ppc.pk:
            existente = EquivalenciaPPC.objects.filter(
                item_novo=novo_ppc, item_anterior=anterior_ppc,
            ).first()
        if existente:
            resultado["existentes"].append({
                "par": par, "equivalencia": existente,
                "item_novo": item_novo, "item_anterior": item_anterior,
            })
            continue

        if aplicar:
            equivalencia = EquivalenciaPPC.objects.create(
                item_novo=novo_ppc, item_anterior=anterior_ppc, criado_por=usuario,
            )
            resultado["criadas"].append({
                "par": par, "equivalencia": equivalencia,
                "item_novo": item_novo, "item_anterior": item_anterior,
            })
        else:
            resultado["criadas"].append({
                "par": par, "item_novo": item_novo,
                "item_anterior": item_anterior,
            })
    return resultado
