"""Contagens agregadas e linhas de detalhe para pendências bibliográficas."""

from django.db.models import Count, Q

from ppc.models import (
    Bibliografia, BibliografiaReferencia, ComponenteNaMatriz,
    ComponenteNaMatrizReferencia, MatrizReferenciaCurricular, PPC,
)


def _linhas_itens(queryset, campos=()):
    return queryset.annotate(
        basicas=Count(
            "bibliografias__referencia_id",
            filter=Q(bibliografias__tipo="basica", bibliografias__referencia_id__isnull=False),
            distinct=True,
        ),
        complementares=Count(
            "bibliografias__referencia_id",
            filter=Q(bibliografias__tipo="complementar", bibliografias__referencia_id__isnull=False),
            distinct=True,
        ),
        fora=Count(
            "bibliografias__pk",
            filter=Q(bibliografias__referencia_id__isnull=True),
            distinct=True,
        ),
    ).values("pk", *campos, "basicas", "complementares", "fora")


def _com_pendencia(linha):
    insuficiente = linha["basicas"] < 3 or linha["complementares"] < 5
    return insuficiente or linha["fora"] > 0, insuficiente


def _agregar_por_entidade(itens, entidade_id, campos):
    saida = {}
    for linha in _linhas_itens(itens, (entidade_id, *campos)):
        entidade = linha[entidade_id]
        agregado = saida.setdefault(entidade, {**{campo: linha.get(campo) for campo in campos},
            "total_componentes": 0, "componentes_pendentes": 0,
            "componentes_minimo_insuficiente": 0, "componentes_fora_biblioteca": 0,
            "bibliografias_fora_biblioteca": 0,
        })
        agregado["total_componentes"] += 1
        pendente, insuficiente = _com_pendencia(linha)
        if pendente:
            agregado["componentes_pendentes"] += 1
        if insuficiente:
            agregado["componentes_minimo_insuficiente"] += 1
        if linha["fora"]:
            agregado["componentes_fora_biblioteca"] += 1
            agregado["bibliografias_fora_biblioteca"] += linha["fora"]
    return saida


def resumo_pendencias_bibliograficas():
    ppcs = _agregar_por_entidade(
        ComponenteNaMatriz.objects, "ppc_id",
        ("ppc__curso_id", "ppc__curso__nome", "ppc__ano_vigencia", "ppc__semestre_vigencia", "ppc__status"),
    )
    matrizes = _agregar_por_entidade(
        ComponenteNaMatrizReferencia.objects, "matriz_id",
        ("matriz__curso_id", "matriz__curso__nome", "matriz__nome", "matriz__identificador_origem"),
    )
    for ppc_id, linha in ppcs.items():
        linha.update({
            "id": ppc_id,
            "curso_id": linha.pop("ppc__curso_id", None),
            "curso_nome": linha.pop("ppc__curso__nome", ""),
            "vigencia": f"{linha.pop('ppc__ano_vigencia', '') or '—'}/{linha.pop('ppc__semestre_vigencia', '') or '—'}",
            "status": linha.pop("ppc__status", ""),
        })
    for matriz_id, linha in matrizes.items():
        linha.update({
            "id": matriz_id,
            "curso_id": linha.pop("matriz__curso_id", None),
            "curso_nome": linha.pop("matriz__curso__nome", "") or "Sem curso vinculado",
            "nome": linha.pop("matriz__nome", "") or linha.pop("matriz__identificador_origem", "") or f"Matriz #{matriz_id}",
        })
    ppcs_com_pendencia = [linha for linha in ppcs.values() if linha["componentes_pendentes"]]
    matrizes_com_pendencia = [linha for linha in matrizes.values() if linha["componentes_pendentes"]]
    return {
        "ppcs": sorted(ppcs_com_pendencia, key=lambda x: ((x["curso_nome"] or "").casefold(), x["id"])),
        "matrizes": sorted(matrizes_com_pendencia, key=lambda x: ((x["curso_nome"] or "").casefold(), x["id"])),
        "total_ppcs": PPC.objects.count(),
        "total_matrizes": MatrizReferenciaCurricular.objects.count(),
        "ppcs_com_pendencia": len(ppcs_com_pendencia),
        "matrizes_com_pendencia": len(matrizes_com_pendencia),
        "ppcs_sem_pendencia": PPC.objects.count() - len(ppcs_com_pendencia),
        "matrizes_sem_pendencia": MatrizReferenciaCurricular.objects.count() - len(matrizes_com_pendencia),
        "componentes_ppc_pendentes": sum(x["componentes_pendentes"] for x in ppcs.values()),
        "componentes_matriz_pendentes": sum(x["componentes_pendentes"] for x in matrizes.values()),
        "bibliografias_fora_biblioteca": sum(x["bibliografias_fora_biblioteca"] for x in ppcs.values()) + sum(x["bibliografias_fora_biblioteca"] for x in matrizes.values()),
    }


def queryset_componentes_pendentes_ppc(ppc_id):
    return _queryset_pendentes(ComponenteNaMatriz.objects.filter(ppc_id=ppc_id).select_related("componente"))


def queryset_componentes_pendentes_matriz(matriz_id):
    return _queryset_pendentes(ComponenteNaMatrizReferencia.objects.filter(matriz_id=matriz_id).select_related("componente"))


def resumo_pendencias_matriz(matriz):
    """Agrega pendências bibliográficas por componente de uma matriz de referência."""
    from ppc.models import RelacaoComponenteReferencia
    from ppc.services.regras_matriz import periodo_relacao_invalido

    linhas = list(_linhas_itens(
        ComponenteNaMatrizReferencia.objects.filter(matriz_id=matriz.pk),
        ("componente__nome", "componente__codigo", "periodo"),
    ))
    por_id = {linha["pk"]: linha for linha in linhas}
    componentes = ComponenteNaMatrizReferencia.objects.filter(
        pk__in=por_id
    ).select_related("componente").order_by("periodo", "ordem")
    pendencias = {}
    for item in componentes:
        linha = por_id[item.pk]
        falta_basicas = max(0, 3 - linha["basicas"])
        falta_complementares = max(0, 5 - linha["complementares"])
        if falta_basicas or falta_complementares or linha["fora"]:
            def quantidade(valor, singular, plural):
                return f"{valor} {singular if valor == 1 else plural}"

            faltantes = []
            if falta_basicas:
                faltantes.append(quantidade(falta_basicas, "básica", "básicas"))
            if falta_complementares:
                faltantes.append(quantidade(falta_complementares, "complementar", "complementares"))
            partes = [f"Faltam {' e '.join(faltantes)}"] if faltantes else []
            if linha["fora"]:
                partes.append(f"{linha['fora']} fora da biblioteca")
            pendencias[item.pk] = "; ".join(partes)

    relacoes = RelacaoComponenteReferencia.objects.filter(
        item__matriz_id=matriz.pk
    ).select_related("item", "item_relacionado")
    invalidas = sum(1 for relacao in relacoes if periodo_relacao_invalido(relacao))
    return {
        "componentes_com_pendencia": len(pendencias),
        "total_componentes": len(linhas),
        "pendencias_por_item": pendencias,
        "relacoes_periodo_invalidas": invalidas,
    }


def _queryset_pendentes(queryset):
    anotado = queryset.annotate(
        basicas=Count("bibliografias__referencia_id", filter=Q(
            bibliografias__tipo="basica", bibliografias__referencia_id__isnull=False,
        ), distinct=True),
        complementares=Count("bibliografias__referencia_id", filter=Q(
            bibliografias__tipo="complementar", bibliografias__referencia_id__isnull=False,
        ), distinct=True),
        fora=Count("bibliografias__pk", filter=Q(
            bibliografias__referencia_id__isnull=True,
        ), distinct=True),
    )
    return anotado.filter(Q(basicas__lt=3) | Q(complementares__lt=5) | Q(fora__gt=0)).prefetch_related("bibliografias")
