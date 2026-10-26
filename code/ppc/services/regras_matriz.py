"""Regras centrais para períodos de PPCs e relações curriculares."""

from django.core.exceptions import ValidationError
from django.db.models import Count, F, Q, Max, Value, IntegerField
from django.db.models.functions import Coalesce


def periodo_relacao_invalido(relacao, periodo_origem=None, periodo_relacionado=None):
    """Retorna mensagem quando a relação viola a ordem dos períodos.

    Em pré-requisito, ``item_relacionado`` é o requisito e deve vir antes
    de ``item``. Em co-requisito, o relacionado pode estar antes ou junto.
    """
    item_origem, periodo_origem_salvo, item_relacionado, periodo_relacionado_salvo, tipo = adaptar_relacao(relacao)
    origem = periodo_origem if periodo_origem is not None else periodo_origem_salvo
    relacionado = periodo_relacionado if periodo_relacionado is not None else periodo_relacionado_salvo
    if tipo == "pre_requisito" and relacionado >= origem:
        return "O pré-requisito deve estar em período estritamente anterior ao componente."
    if tipo == "co_requisito" and relacionado > origem:
        return "O co-requisito não pode estar em período posterior ao componente."
    return None


def adaptar_relacao(relacao):
    """Unifica os dois modelos de relação sem duplicar as regras de período."""
    if hasattr(relacao, "componente_na_matriz_id"):
        origem = relacao.componente_na_matriz
        relacionado = relacao.componente_relacionado_na_matriz
    else:
        origem = relacao.item
        relacionado = relacao.item_relacionado
    return origem, origem.periodo, relacionado, relacionado.periodo, relacao.tipo


def validar_relacao_periodo(relacao, periodo_origem=None, periodo_relacionado=None):
    mensagem = periodo_relacao_invalido(relacao, periodo_origem, periodo_relacionado)
    if mensagem:
        raise ValidationError(mensagem)


def validar_mudanca_periodo(item, novo_periodo, tipo):
    """Impede mudança que crie relação inválida em qualquer ponta."""
    if not item.pk:
        return
    from ppc.models import RelacaoComponente, RelacaoComponenteReferencia

    if tipo == "ppc":
        relacoes = RelacaoComponente.objects.filter(
            componente_na_matriz__ppc=item.ppc
        ).filter(
            componente_na_matriz_id=item.pk
        ) | RelacaoComponente.objects.filter(
            componente_relacionado_na_matriz_id=item.pk
        )
        for relacao in relacoes.select_related(
            "componente_na_matriz", "componente_relacionado_na_matriz"
        ):
            origem = novo_periodo if relacao.componente_na_matriz_id == item.pk else None
            relacionado = novo_periodo if relacao.componente_relacionado_na_matriz_id == item.pk else None
            validar_relacao_periodo(relacao, origem, relacionado)
    else:
        relacoes = RelacaoComponenteReferencia.objects.filter(
            item_id=item.pk
        ) | RelacaoComponenteReferencia.objects.filter(item_relacionado_id=item.pk)
        for relacao in relacoes.select_related("item", "item_relacionado"):
            origem = novo_periodo if relacao.item_id == item.pk else None
            relacionado = novo_periodo if relacao.item_relacionado_id == item.pk else None
            validar_relacao_periodo(relacao, origem, relacionado)


def maior_periodo_ppc(ppc):
    return ppc.matriz_componentes.order_by("-periodo").values_list("periodo", flat=True).first() or 0


def validar_periodo_ppc(ppc, periodo):
    if periodo is None or periodo < 1:
        raise ValidationError({"periodo": "O período deve ser maior que zero."})
    if ppc.duracao_maxima_semestres and periodo > ppc.duracao_maxima_semestres:
        raise ValidationError({
            "periodo": f"O período {periodo} excede a duração máxima de {ppc.duracao_maxima_semestres} semestres deste PPC."
        })


def validar_status_e_duracoes(
    ppc, *, minimo=None, media=None, maximo=None, status=None,
    status_original=None, maximo_original=None, validar_duracoes=True,
):
    minimo = ppc.duracao_minima_semestres if minimo is None else minimo
    media = ppc.duracao_media_semestres if media is None else media
    maximo = ppc.duracao_maxima_semestres if maximo is None else maximo
    status = ppc.status if status is None else status
    status_original = ppc.status if status_original is None else status_original
    maximo_original = ppc.duracao_maxima_semestres if maximo_original is None else maximo_original
    mudou_para_status_final = status != status_original and status in {"em_revisao", "aprovado"}
    if mudou_para_status_final and not (minimo and media and maximo):
        raise ValidationError("Informe as durações mínima, média e máxima do PPC.")
    if minimo is None or media is None or maximo is None:
        return
    anterior = None
    if ppc.pk:
        anterior = type(ppc).objects.filter(pk=ppc.pk).values(
            "duracao_minima_semestres", "duracao_media_semestres", "duracao_maxima_semestres"
        ).first()
    if validar_duracoes and not (minimo <= media <= maximo):
        raise ValidationError("A duração mínima deve ser menor ou igual à média, e a média menor ou igual à máxima.")
    maior = maior_periodo_ppc(ppc) if ppc.pk else 0
    if maior > maximo and (not ppc.pk or maximo != maximo_original):
        raise ValidationError(f"A duração máxima não pode ser menor que o maior período já utilizado ({maior}).")
    if (not ppc.pk or status != status_original) and status in {"em_revisao", "aprovado"} and maior < minimo:
        raise ValidationError(f"Para mudar o status, a matriz precisa alcançar ao menos {minimo} períodos; atualmente alcança {maior}.")


def pendencias_referencias(componentes, *, relacionamento="bibliografias"):
    """Pendências derivadas por vínculo, sem persistir estados calculados."""
    resultado = []
    for item in componentes:
        refs = list(getattr(item, relacionamento).all())
        basicas = {bib.referencia_id for bib in refs if bib.tipo == "basica" and bib.referencia_id}
        complementares = {bib.referencia_id for bib in refs if bib.tipo == "complementar" and bib.referencia_id}
        fora = sum(1 for bib in refs if not bib.referencia_id)
        faltam_b = max(0, 3 - len(basicas))
        faltam_c = max(0, 5 - len(complementares))
        if fora or faltam_b or faltam_c:
            resultado.append({
                "item": item, "fora_biblioteca": fora,
                "basicas": len(basicas), "complementares": len(complementares),
                "faltam_basicas": faltam_b, "faltam_complementares": faltam_c,
            })
    return resultado


def relacoes_invalidas():
    from ppc.models import RelacaoComponente, RelacaoComponenteReferencia
    saida = []
    for relacao in RelacaoComponente.objects.select_related(
        "componente_na_matriz__ppc__curso", "componente_na_matriz__componente",
        "componente_relacionado_na_matriz__componente",
    ):
        mensagem = periodo_relacao_invalido(relacao)
        if mensagem:
            saida.append({"relacao": relacao, "mensagem": mensagem, "escopo": "PPC"})
    for relacao in RelacaoComponenteReferencia.objects.select_related(
        "item__matriz__curso", "item__componente", "item_relacionado__componente",
    ):
        mensagem = periodo_relacao_invalido(relacao)
        if mensagem:
            saida.append({"relacao": relacao, "mensagem": mensagem, "escopo": "Matriz de referência"})
    return saida


def contar_relacoes_invalidas():
    from ppc.models import RelacaoComponente, RelacaoComponenteReferencia

    tipos_invalidos_ppc = (
        Q(tipo="pre_requisito", componente_relacionado_na_matriz__periodo__gte=F("componente_na_matriz__periodo"))
        | Q(tipo="co_requisito", componente_relacionado_na_matriz__periodo__gt=F("componente_na_matriz__periodo"))
    )
    tipos_invalidos_referencia = (
        Q(tipo="pre_requisito", item_relacionado__periodo__gte=F("item__periodo"))
        | Q(tipo="co_requisito", item_relacionado__periodo__gt=F("item__periodo"))
    )
    return (
        RelacaoComponente.objects.filter(tipos_invalidos_ppc).aggregate(total=Count("pk"))["total"]
        + RelacaoComponenteReferencia.objects.filter(tipos_invalidos_referencia).aggregate(total=Count("pk"))["total"]
    )


def ppcs_fora_da_duracao_queryset():
    from ppc.models import PPC
    return PPC.objects.annotate(
        maior_periodo_usado=Coalesce(Max("matriz_componentes__periodo"), Value(0), output_field=IntegerField())
    ).filter(
        Q(duracao_maxima_semestres__gt=0, maior_periodo_usado__gt=F("duracao_maxima_semestres"))
        | Q(maior_periodo_usado__lt=F("duracao_minima_semestres"))
    )
