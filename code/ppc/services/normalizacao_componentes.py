from __future__ import annotations

import re
from typing import Any

import pandas as pd


def _valor_str(valor: Any) -> str:
    """
    Converte o valor da célula para str sem transformar NaN em 'nan'.

    Para identificadores numéricos vindos do Excel, evita o sufixo '.0'
    quando o pandas tiver inferido o valor como float.
    """
    if pd.isna(valor):
        return ""

    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))

    return str(valor).strip()


def _valor_int(valor: Any, nome_campo: str, linha_origem: int) -> int:
    """
    Converte uma célula para inteiro.

    O import deve falhar explicitamente se um campo obrigatório que
    deveria ser inteiro estiver inválido, em vez de inventar um valor.
    """
    if pd.isna(valor):
        raise ValueError(
            f"Campo '{nome_campo}' ausente na linha {linha_origem}."
        )

    try:
        return int(valor)
    except (TypeError, ValueError):
        raise ValueError(
            f"Campo '{nome_campo}' inválido na linha {linha_origem}: {valor!r}"
        )


def _normalizar_nucleo(
    valor_nucleo: Any,
) -> tuple[str | None, str | None, str, str | None]:
    """
    Normaliza o núcleo do item da matriz.

    Importante:
    'nucleo' e 'natureza' são atributos do vínculo do componente
    com a matriz, não do catálogo ComponenteCurricular.

    Retorna:
        (nucleo, natureza, confianca, motivo_ambiguidade)

    Regras:
    - NÚCLEO COMUM
        -> NC / obrigatoria / determinada

    - NÚCLEO ESPECÍFICO OBRIGATÓRIO
        -> NE / obrigatoria / determinada

    - NÚCLEO ESPECÍFICO OPTATIVO
        -> NE / optativa / determinada

    - Qualquer valor não reconhecido
        -> None / None / ambigua
    """
    if pd.isna(valor_nucleo):
        return (
            None,
            None,
            "ambigua",
            "Campo núcleo está vazio ou ausente",
        )

    nucleo_original = str(valor_nucleo).strip()

    nucleo_normalizado = re.sub(
        r"\s+",
        " ",
        nucleo_original.upper(),
    ).strip()

    # Núcleo Comum:
    # pela nova regra, NC é sempre obrigatório.
    if nucleo_normalizado == "NÚCLEO COMUM":
        return (
            "NC",
            "obrigatoria",
            "determinada",
            None,
        )

    # Núcleo Específico Obrigatório
    if nucleo_normalizado == "NÚCLEO ESPECÍFICO OBRIGATÓRIO":
        return (
            "NE",
            "obrigatoria",
            "determinada",
            None,
        )

    # Núcleo Específico Optativo
    if nucleo_normalizado == "NÚCLEO ESPECÍFICO OPTATIVO":
        return (
            "NE",
            "optativa",
            "determinada",
            None,
        )

    # Não tentar inferir outros valores.
    return (
        None,
        None,
        "ambigua",
        f"Valor de núcleo não reconhecido: {nucleo_original!r}",
    )

def _valor_int_opcional(
    valor: Any,
    nome_campo: str,
    linha_origem: int,
) -> int | None:
    if pd.isna(valor):
        return None

    try:
        return int(valor)
    except (TypeError, ValueError):
        raise ValueError(
            f"Campo '{nome_campo}' inválido na linha "
            f"{linha_origem}: {valor!r}"
        )


def normalizar_planilha_matriz(caminho_arquivo: str) -> list[dict]:
    """
    Lê a planilha de componentes curriculares e transforma cada linha
    em um dicionário no formato definido pelo contrato do importador.

    Importante:
    - Não deduplica.
    - Não descarta linhas.
    - Não altera a identificação de origem.
    - Não inventa natureza quando ela não pode ser determinada.
    - Não deriva tipo de componente sem uma coluna explícita na fonte.

    A coluna 'fase' da planilha é usada como 'periodo'.
    A coluna 'ementa' da planilha é usada diretamente como 'ementa'.
    """
    df = pd.read_excel(caminho_arquivo)

    colunas_obrigatorias = {
        "matriz_curricular",
        "codigo",
        "nucleo",
        "disciplina",
        "fase",
        "cargahorariateorica",
        "cargahorariapratica",
        "ementa",
    }

    colunas_ausentes = colunas_obrigatorias - set(df.columns)

    if colunas_ausentes:
        raise ValueError(
            "A planilha não possui todas as colunas obrigatórias. "
            f"Ausentes: {sorted(colunas_ausentes)}"
        )

    resultado: list[dict] = []

    for indice, linha in df.iterrows():
        # Excel: linha 1 = cabeçalho.
        # DataFrame: índice 0 = primeira linha de dados.
        linha_origem = indice + 2

        carga_horaria_acex = _valor_int_opcional(
            linha["cargahorariaacex"],
            "cargahorariaacex",
            linha_origem,
        )

        identificador_origem = _valor_str(
            linha["matriz_curricular"]
        )

        codigo = _valor_str(
            linha["codigo"]
        )

        nome = _valor_str(
            linha["disciplina"]
        )

        periodo = _valor_int(
            linha["fase"],
            "fase",
            linha_origem,
        )

        carga_horaria_teorica = _valor_int(
            linha["cargahorariateorica"],
            "cargahorariateorica",
            linha_origem,
        )

        carga_horaria_pratica = _valor_int(
            linha["cargahorariapratica"],
            "cargahorariapratica",
            linha_origem,
        )

        ementa = _valor_str(
            linha["ementa"]
        )

        (
            nucleo,
            natureza,
            confianca,
            motivo_ambiguidade,
        ) = _normalizar_nucleo(
            linha["nucleo"]
        )

        resultado.append(
            {
                "identificador_origem": identificador_origem,
                "codigo": codigo,
                "nome": nome,
                "nucleo": nucleo,
                "natureza": natureza,
                "periodo": periodo,
                "confianca": confianca,
                "motivo_ambiguidade": motivo_ambiguidade,
                "linha_origem": linha_origem,

                # Campos adicionais confirmados na planilha:
                "carga_horaria_teorica": carga_horaria_teorica,
                "carga_horaria_pratica": carga_horaria_pratica,
                "carga_horaria_acex": carga_horaria_acex,
                "ementa": ementa,
            }
        )

    return resultado