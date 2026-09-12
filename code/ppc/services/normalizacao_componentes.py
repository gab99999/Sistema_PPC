
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
    Normaliza o campo 'nucleo'.

    Retorna:
        (nucleo, natureza, confianca, motivo_ambiguidade)

    Regras:
    - NÚCLEO ESPECÍFICO OBRIGATÓRIO -> NE / obrigatoria
    - NÚCLEO ESPECÍFICO OPTATIVO   -> NE / optativa
    - NÚCLEO COMUM                 -> NC / None / ambigua
    - padrão desconhecido          -> None / None / ambigua
    """
    if pd.isna(valor_nucleo):
        return (
            None,
            None,
            "ambigua",
            "Campo núcleo está vazio ou ausente",
        )

    nucleo_original = str(valor_nucleo).strip()

    # Normalização apenas para facilitar a comparação.
    # Não usamos essa versão para armazenar o valor original.
    nucleo_normalizado = re.sub(
        r"\s+",
        " ",
        nucleo_original.upper(),
    ).strip()

    # 1. Núcleo específico obrigatório
    if nucleo_normalizado == "NÚCLEO ESPECÍFICO OBRIGATÓRIO":
        return (
            "NE",
            "obrigatoria",
            "determinada",
            None,
        )

    # 2. Núcleo específico optativo
    if nucleo_normalizado == "NÚCLEO ESPECÍFICO OPTATIVO":
        return (
            "NE",
            "optativa",
            "determinada",
            None,
        )

    # 3. Núcleo comum sem natureza explícita
    if nucleo_normalizado == "NÚCLEO COMUM":
        return (
            "NC",
            None,
            "ambigua",
            "Núcleo comum não define natureza obrigatória/optativa por si só",
        )

    # 4. Não tentar adivinhar outros valores.
    return (
        None,
        None,
        "ambigua",
        f"Valor de núcleo não reconhecido: {nucleo_original!r}",
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

        identificador_origem = _valor_str(
            linha["matriz_curricular"]
        )

        codigo = _valor_str(linha["codigo"])
        nome = _valor_str(linha["disciplina"])

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

        (
            nucleo,
            natureza,
            confianca,
            motivo_ambiguidade,
        ) = _normalizar_nucleo(linha["nucleo"])

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
            }
        )

    return resultado


# ============================================================
# TESTES RÁPIDOS
# ============================================================

if __name__ == "__main__":
    CAMINHO = "componentes_curriculares.xlsx"

    dados = normalizar_planilha_matriz(CAMINHO)

    print(f"Total de linhas normalizadas: {len(dados)}")
    assert len(dados) == 4913

    # --------------------------------------------------------
    # Caso determinado: Núcleo Específico Obrigatório
    # Exemplo real da planilha:
    # linha 15:
    # CGN0139 - FUNDAMENTOS DO AGRONEGÓCIO
    # --------------------------------------------------------
    exemplo_obrigatoria = next(
        item
        for item in dados
        if item["codigo"] == "CGN0139"
        and item["identificador_origem"] == "1657712"
    )

    assert exemplo_obrigatoria["nucleo"] == "NE"
    assert exemplo_obrigatoria["natureza"] == "obrigatoria"
    assert exemplo_obrigatoria["confianca"] == "determinada"
    assert exemplo_obrigatoria["motivo_ambiguidade"] is None
    assert exemplo_obrigatoria["periodo"] == 1
    assert exemplo_obrigatoria["linha_origem"] == 15
    assert exemplo_obrigatoria["carga_horaria_teorica"] == 64
    assert exemplo_obrigatoria["carga_horaria_pratica"] == 0

    print("OK - caso obrigatório:")
    print(exemplo_obrigatoria)

    # --------------------------------------------------------
    # Caso determinado: Núcleo Específico Optativo
    # Exemplo real da planilha:
    # ADM-BN-1C / ILL0066 / LÍNGUA BRASILEIRA DE SINAIS
    # --------------------------------------------------------
    exemplo_optativa = next(
        item
        for item in dados
        if item["codigo"] == "ILL0066"
        and item["identificador_origem"] == "ADM-BN-1C"
    )

    assert exemplo_optativa["nucleo"] == "NE"
    assert exemplo_optativa["natureza"] == "optativa"
    assert exemplo_optativa["confianca"] == "determinada"
    assert exemplo_optativa["motivo_ambiguidade"] is None
    assert exemplo_optativa["periodo"] == 1
    assert exemplo_optativa["linha_origem"] == 91

    print("\nOK - caso optativo:")
    print(exemplo_optativa)

    # --------------------------------------------------------
    # Caso ambíguo real da planilha:
    # QUIM-LN-2C / CGN0026 / EMPREENDEDORISMO
    # linha 4801
    # núcleo = NÚCLEO ESPECÍFICO
    # --------------------------------------------------------
    exemplo_ambiguo = next(
        item
        for item in dados
        if item["codigo"] == "CGN0026"
        and item["identificador_origem"] == "QUIM-LN-2C"
        and item["linha_origem"] == 4801
    )

    assert exemplo_ambiguo["nucleo"] is None
    assert exemplo_ambiguo["natureza"] is None
    assert exemplo_ambiguo["confianca"] == "ambigua"
    assert (
        exemplo_ambiguo["motivo_ambiguidade"]
        == "Valor de núcleo não reconhecido: 'NÚCLEO ESPECÍFICO'"
    )
    assert exemplo_ambiguo["periodo"] == 9
    assert exemplo_ambiguo["carga_horaria_teorica"] == 64
    assert exemplo_ambiguo["carga_horaria_pratica"] == 0

    print("\nOK - caso ambíguo:")
    print(exemplo_ambiguo)

    # --------------------------------------------------------
    # Verificação importante:
    # nenhuma linha foi deduplicada.
    # --------------------------------------------------------
    print("\nTodos os testes passaram.")

