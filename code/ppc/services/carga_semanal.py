"""Cálculo da carga semanal para vínculos de matriz e de PPC."""

from decimal import Decimal, ROUND_HALF_UP


SEMANAS_POR_SEMESTRE = 16


def _formatar(valor):
    arredondado = Decimal(valor).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    texto = format(arredondado, "f").rstrip("0").rstrip(".")
    return texto.replace(".", ",") or "0"


def formatar_horas_semanais_valor(valor):
    """Formata valor semanal com vírgula e sem zeros decimais desnecessários."""
    return _formatar(Decimal(str(valor or 0)))


def calcular_horas_semanais(itens):
    """Retorna por vínculo carga semanal total e seus componentes para exibição.

    Aceita ComponenteNaMatrizReferencia e ComponenteNaMatriz, que compartilham
    o atributo ``componente``.
    """
    resultado = {}
    divisor = Decimal(SEMANAS_POR_SEMESTRE)
    for item in itens:
        componente = item.componente
        if componente.tipo == "atividade":
            estudante = Decimal(componente.carga_horaria_estudante or 0) / divisor
            teorica = pratica = Decimal("0")
            total = estudante
            detalhe = f"Estudante: {_formatar(estudante)} h/sem"
        else:
            teorica = Decimal(componente.carga_horaria_teorica or 0) / divisor
            pratica = Decimal(componente.carga_horaria_pratica or 0) / divisor
            total = teorica + pratica
            detalhe = f"Teórica: {_formatar(teorica)} h/sem · Prática: {_formatar(pratica)} h/sem"
        resultado[item.pk] = {
            "total": float(total),
            "teorica": float(teorica),
            "pratica": float(pratica),
            "texto": f"{_formatar(total)} h/sem",
            "detalhe": detalhe,
            "atividade": componente.tipo == "atividade",
        }
    return resultado
