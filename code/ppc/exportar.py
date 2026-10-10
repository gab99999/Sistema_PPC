from django.shortcuts import get_object_or_404
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.db.models import Prefetch

from weasyprint import HTML

from .models import (
    PPC,
    ComponenteNaMatriz,
    RelacaoComponente,
    GrupoEquivalenciaComponentes,
    ItemEquivalencia,
)

from .services.carga_horaria import calcular_resumo_carga_horaria


def gerar_pdf_ppc(request, ppc_id):
    ppc = get_object_or_404(
        PPC.objects.select_related("curso"),
        pk=ppc_id,
    )

    # =========================================================
    # DATAS / RESOLUÇÃO
    # =========================================================

    numero_resolucao = ppc.numero_resolucao or "[A DEFINIR]"

    data_reuniao = ppc.data_aprovacao or ppc.data_resolucao
    data_resolucao = ppc.data_resolucao or ppc.data_aprovacao

    meses = [
        "",
        "janeiro",
        "fevereiro",
        "março",
        "abril",
        "maio",
        "junho",
        "julho",
        "agosto",
        "setembro",
        "outubro",
        "novembro",
        "dezembro",
    ]

    def data_extenso(data):
        if not data:
            return "[A DEFINIR]"

        return (
            f"{data.day:02d} de "
            f"{meses[data.month]} de "
            f"{data.year}"
        )

    data_reuniao_texto = data_extenso(data_reuniao)
    data_resolucao_texto = data_extenso(data_resolucao)

    semestre_vigencia_texto = (
        "primeiro"
        if ppc.semestre_vigencia == 1
        else "segundo"
    )

    # =========================================================
    # COMPONENTES DA MATRIZ
    # =========================================================

    relacoes_qs = (
        RelacaoComponente.objects
        .select_related(
            "componente_relacionado_na_matriz__componente"
        )
        .order_by("tipo", "id")
    )

    componentes_na_matriz = list(
        ComponenteNaMatriz.objects
        .filter(ppc=ppc)
        .select_related("componente")
        .prefetch_related(
            "bibliografias",
            Prefetch(
                "relacoes",
                queryset=relacoes_qs,
                to_attr="relacoes_pdf",
            ),
        )
        .order_by("periodo", "id")
    )

    matriz_linhas = []

    for item in componentes_na_matriz:
        relacoes = getattr(
            item,
            "relacoes_pdf",
            [],
        )

        pre_requisitos = []
        co_requisitos = []

        for relacao in relacoes:
            nome_relacionado = (
                relacao
                .componente_relacionado_na_matriz
                .componente
                .nome
            )

            if relacao.tipo == "pre_requisito":
                pre_requisitos.append(nome_relacionado)

            elif relacao.tipo == "co_requisito":
                co_requisitos.append(nome_relacionado)

        ccu = item.componente.ccu

        if ccu is True:
            ccu_display = "Sim"
        elif ccu is False:
            ccu_display = "Não"
        else:
            ccu_display = "—"

        matriz_linhas.append({
            "nome": item.componente.nome,

            "unidade": (
                item.componente.unidade_academica_componente
                or "—"
            ),

            "ccu": ccu_display,

            "ch_teorica": (
                item.componente.carga_horaria_teorica
            ),

            "ch_pratica": (
                item.componente.carga_horaria_pratica
            ),

            "ch_pcc": (
                item.componente.carga_horaria_pcc
            ),

            "ch_acex": (
                item.componente.carga_horaria_acex or 0
            ),

            "ch_total": (
                item.componente.carga_horaria_computada_total
            ),

            "pre_requisitos": pre_requisitos,
            "co_requisitos": co_requisitos,

            "nucleo": (
                item.get_nucleo_display()
            ),

            "natureza": (
                item.get_natureza_display()
            ),

            "tipo": (
                item.componente.get_tipo_display()
            ),

            "periodo": item.periodo,

            # Mantém o objeto para a seção de ementas.
            "objeto": item,
        })

    # =========================================================
    # BIBLIOGRAFIAS PRONTAS PARA O TEMPLATE
    # =========================================================

    for item in componentes_na_matriz:
        basicas = []
        complementares = []

        for bib in item.bibliografias.all():
            if bib.tipo == "basica":
                basicas.append(bib)
            elif bib.tipo == "complementar":
                complementares.append(bib)

        item.bibliografias_basicas = basicas
        item.bibliografias_complementares = complementares

    # =========================================================
    # QUADRO RESUMO DE CARGA HORÁRIA
    # =========================================================

    resumo = calcular_resumo_carga_horaria(ppc)

    def percentual_br(valor):
        if valor is None:
            return "—"

        return f"{float(valor):.2f}%".replace(".", ",")

    resumo_carga_horaria = [
        {
            "nome": "CH de Núcleo Comum (NC)",
            "ch": resumo["nc"]["ch"],
            "pct": percentual_br(resumo["nc"]["pct"]),
            "negrito": False,
        },
        {
            "nome": "CH de Núcleo Específico Obrigatório (NEObrig)",
            "ch": resumo["ne_obrig"]["ch"],
            "pct": percentual_br(resumo["ne_obrig"]["pct"]),
            "negrito": False,
        },
        {
            "nome": "CH de Núcleo Específico Optativo (NEOptat)",
            "ch": resumo["ne_optat"]["ch"],
            "pct": percentual_br(resumo["ne_optat"]["pct"]),
            "negrito": False,
        },
        {
            "nome": "CH de Núcleo Livre (NL)",
            "ch": resumo["nl"]["ch"],
            "pct": percentual_br(resumo["nl"]["pct"]),
            "negrito": False,
        },
        {
            "nome": "CH Mínima DE Seminário de Integração",
            "ch": resumo["seminario"]["ch"],
            "pct": percentual_br(resumo["seminario"]["pct"]),
            "negrito": False,
        },
        {
            "nome": (
                "CH de Atividades Curriculares de Extensão (ACEx) "
                "em componentes obrigatórios"
            ),
            "ch": resumo["acex_obrig"]["ch"],
            "pct": percentual_br(resumo["acex_obrig"]["pct"]),
            "negrito": False,
        },
        {
            "nome": (
                "CH de Atividades Curriculares de Extensão (ACEx) "
                "em componentes optativos"
            ),
            "ch": resumo["acex_optat"]["ch"],
            "pct": percentual_br(resumo["acex_optat"]["pct"]),
            "negrito": False,
        },
        {
            "nome": (
                "CH de Atividades Curriculares de Extensão (ACEx) "
                "em componentes de núcleo livre"
            ),
            "ch": resumo["acex_nl"]["ch"],
            "pct": percentual_br(resumo["acex_nl"]["pct"]),
            "negrito": True,
        },
        {
            "nome": (
                "CH de Atividades Curriculares de Extensão (ACEx) "
                "em ação de extensão"
            ),
            "ch": resumo["acex_extensao"]["ch"],
            "pct": percentual_br(resumo["acex_extensao"]["pct"]),
            "negrito": True,
        },
        {
            "nome": "CH Mínima de Atividades Complementares (AC)",
            "ch": resumo["ac"]["ch"],
            "pct": percentual_br(resumo["ac"]["pct"]),
            "negrito": True,
        },
    ]

    # =========================================================
    # QUADRO DE EQUIVALÊNCIA
    # =========================================================

    itens_equivalencia_qs = (
        ItemEquivalencia.objects
        .filter(
            item_matriz__matriz__curso=ppc.curso
        )
        .select_related(
            "item_matriz__componente",
            "item_matriz__matriz",
        )
        .order_by("ordem", "id")
    )

    grupos_equivalencia = list(
        GrupoEquivalenciaComponentes.objects
        .filter(
            itens__item_matriz__matriz__curso=ppc.curso
        )
        .distinct()
        .prefetch_related(
            Prefetch(
                "itens",
                queryset=itens_equivalencia_qs,
                to_attr="itens_pdf",
            )
        )
        .order_by("id")
    )

    # Maior posição de ordem existente em qualquer grupo.
    equivalencia_max_ordem = max(
        (
            item.ordem
            for grupo in grupos_equivalencia
            for item in getattr(grupo, "itens_pdf", [])
        ),
        default=0,
    )

    equivalencia_colunas_lista = list(
        range(1, equivalencia_max_ordem + 1)
    )

    equivalencia_linhas = []

    for grupo in grupos_equivalencia:
        # Começa todas as células vazias.
        linha = ["—"] * equivalencia_max_ordem

        for item in getattr(grupo, "itens_pdf", []):
            ordem = item.ordem

            if ordem < 1:
                continue

            codigo = (
                item.item_matriz
                .componente
                .codigo
            )

            codigo = codigo or "—"

            # ordem=1 -> índice 0
            # ordem=2 -> índice 1
            # etc.
            linha[ordem - 1] = codigo

        equivalencia_linhas.append(linha)

    # =========================================================
    # CONTEXTO
    # =========================================================

    context = {
        "ppc": ppc,

        # Abertura / resolução
        "numero_resolucao": numero_resolucao,
        "data_reuniao_texto": data_reuniao_texto,
        "data_resolucao_texto": data_resolucao_texto,
        "semestre_vigencia_texto": semestre_vigencia_texto,

        # Matriz
        "componentes_na_matriz": componentes_na_matriz,
        "matriz_linhas": matriz_linhas,

        # Resumo
        "resumo_carga_horaria": resumo_carga_horaria,

        # Equivalência
        "equivalencia_colunas": equivalencia_max_ordem,
        "equivalencia_colunas_lista": equivalencia_colunas_lista,
        "equivalencia_linhas": equivalencia_linhas,
    }

    # =========================================================
    # RENDERIZAÇÃO HTML
    # =========================================================

    html_renderizado = render_to_string(
        "ppc/pdf/ppc_documento.html",
        context,
        request=request,
    )

    # =========================================================
    # CONVERSÃO HTML -> PDF COM WEASYPRINT
    # =========================================================

    pdf = HTML(
        string=html_renderizado,
        base_url=request.build_absolute_uri(),
    ).write_pdf()

    # =========================================================
    # RESPOSTA HTTP
    # =========================================================

    response = HttpResponse(
        pdf,
        content_type="application/pdf",
    )

    response["Content-Disposition"] = (
        f'attachment; filename="PPC_{ppc.curso.nome}.pdf"'
    )

    return response