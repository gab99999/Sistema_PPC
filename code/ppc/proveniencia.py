"""Semântica e correspondência estrutural para importação de PPCs.

Esta camada não persiste dados e não altera a obrigatoriedade dos modelos.
Ela conserva a diferença entre dado extraído, ausência comprovada no documento
e dado que a extração não conseguiu localizar.
"""

from __future__ import annotations

import re
from typing import Any


PRESENTE_NO_DOCUMENTO = "PRESENTE_NO_DOCUMENTO"
AUSENTE_COMPROVADO_NO_DOCUMENTO = "AUSENTE_COMPROVADO_NO_DOCUMENTO"
NAO_LOCALIZADO = "NAO_LOCALIZADO"
VALOR_SEMANTICO_EXPLICITO = "VALOR_SEMANTICO_EXPLICITO"

ESTADOS_PROVENIENCIA = {
    PRESENTE_NO_DOCUMENTO,
    AUSENTE_COMPROVADO_NO_DOCUMENTO,
    NAO_LOCALIZADO,
    VALOR_SEMANTICO_EXPLICITO,
}


def valor_ausente(valor: Any) -> bool:
    """`0` é dado presente; somente nulo/string vazia representa ausência."""
    return valor is None or valor == ""


def caminho_corresponde(padrao: str, caminho: str) -> bool:
    """Compara caminhos estruturais completos, aceitando ``[*]`` em listas."""
    expressao = re.escape(padrao).replace(r"\[\*\]", r"\[\d+\]")
    return re.fullmatch(expressao, caminho) is not None


def achatar_campos(valor: Any, caminho: str = "") -> dict[str, Any]:
    """Produz caminhos indexados para folhas de dict/list, inclusive valores nulos."""
    if isinstance(valor, dict):
        resultado: dict[str, Any] = {}
        for chave, filho in valor.items():
            proximo = f"{caminho}.{chave}" if caminho else chave
            resultado.update(achatar_campos(filho, proximo))
        return resultado
    if isinstance(valor, list):
        resultado = {}
        for indice, filho in enumerate(valor):
            resultado.update(achatar_campos(filho, f"{caminho}[{indice}]"))
        return resultado
    return {caminho: valor}


def _registro_ausencia_legado(item: dict[str, Any]) -> dict[str, str]:
    return {
        "caminho": item["caminho"],
        "estado": AUSENTE_COMPROVADO_NO_DOCUMENTO,
        "evidencia": item["motivo"],
    }


def normalizar_proveniencia(dados: dict[str, Any]) -> list[dict[str, str]]:
    """Normaliza a fonte canônica e aceita o campo legado apenas como apoio.

    ``proveniencia_campos`` é a fonte de verdade.  ``ausencias_no_documento``
    existe para consumidores antigos e pode repetir a mesma ausência com uma
    redação de evidência diferente; essa cópia não pode transformar uma
    resposta válida em conflito nem sobrepor a informação canônica.
    """
    registros = list(dados.get("proveniencia_campos", []))
    caminhos_canonicos = {
        item.get("caminho") for item in registros if isinstance(item, dict)
    }
    registros.extend(
        _registro_ausencia_legado(item)
        for item in dados.get("ausencias_no_documento", [])
        if isinstance(item, dict) and item.get("caminho") not in caminhos_canonicos
    )
    normalizados: list[dict[str, str]] = []
    por_caminho: dict[str, dict[str, str]] = {}
    for item in registros:
        if not isinstance(item, dict):
            raise ValueError("Cada registro de proveniência deve ser um objeto JSON.")
        caminho, estado = item.get("caminho"), item.get("estado")
        evidencia = item.get("evidencia", item.get("motivo"))
        if not isinstance(caminho, str) or not caminho:
            raise ValueError("Todo registro de proveniência precisa de um caminho não vazio.")
        if estado not in ESTADOS_PROVENIENCIA:
            raise ValueError(f"Estado de proveniência inválido em '{caminho}': {estado!r}.")
        if not isinstance(evidencia, str) or not evidencia.strip():
            raise ValueError(f"Todo registro de proveniência precisa de evidência em '{caminho}'.")
        registro = {"caminho": caminho, "estado": estado, "evidencia": evidencia.strip()}
        anterior = por_caminho.get(caminho)
        if anterior and anterior != registro:
            raise ValueError(f"Há proveniências conflitantes para '{caminho}'.")
        por_caminho[caminho] = registro
    normalizados.extend(por_caminho.values())
    return normalizados


def validar_proveniencia(dados: dict[str, Any], registros: list[dict[str, str]]) -> None:
    """Impede que uma classificação documental masque valor perdido pela IA."""
    campos = achatar_campos({chave: valor for chave, valor in dados.items() if chave not in {
        "proveniencia_campos", "ausencias_no_documento"
    }})
    for registro in registros:
        caminho, estado = registro["caminho"], registro["estado"]
        encontrados = {chave: valor for chave, valor in campos.items() if caminho_corresponde(caminho, chave)}
        # Coleções vazias não possuem folhas para validar; o curinga continua válido.
        if not encontrados and "[*]" not in caminho:
            raise ValueError(f"O caminho de proveniência não existe nos dados: '{caminho}'.")
        if estado == AUSENTE_COMPROVADO_NO_DOCUMENTO and any(
            not valor_ausente(valor) for valor in encontrados.values()
        ):
            raise ValueError(f"'{caminho}' foi marcado como ausente, mas possui valor extraído.")
        if estado == NAO_LOCALIZADO and any(not valor_ausente(valor) for valor in encontrados.values()):
            raise ValueError(f"'{caminho}' foi marcado como não localizado, mas possui valor extraído.")
        if estado in {PRESENTE_NO_DOCUMENTO, VALOR_SEMANTICO_EXPLICITO} and any(
            valor_ausente(valor) for valor in encontrados.values()
        ):
            raise ValueError(f"'{caminho}' foi marcado como presente, mas não possui valor.")


def proveniencia_do_caminho(caminho: str, registros: list[dict[str, str]], valor: Any) -> dict[str, str]:
    """Obtém a proveniência mais específica; sem registro, infere presente/não localizado."""
    exatos = [item for item in registros if item["caminho"] == caminho]
    curingas = [item for item in registros if caminho_corresponde(item["caminho"], caminho)]
    candidato = (exatos or curingas)
    if candidato:
        return candidato[0]
    return {
        "caminho": caminho,
        "estado": PRESENTE_NO_DOCUMENTO if not valor_ausente(valor) else NAO_LOCALIZADO,
        "evidencia": "Estado inferido a partir do valor extraído; não há declaração documental explícita.",
    }


def classificar_erros_formulario(
    erros: dict[str, Any], caminho_base: str, registros: list[dict[str, str]], dados_enviados: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Classifica somente ausência comprovada como pendência não bloqueante."""
    pendencias, bloqueantes = [], []
    for campo, mensagens in erros.items():
        caminho = f"{caminho_base}.{campo}" if caminho_base else campo
        proveniencia = proveniencia_do_caminho(caminho, registros, dados_enviados.get(campo))
        item = {
            "caminho": caminho,
            "campo": campo,
            "erros": mensagens,
            "estado_proveniencia": proveniencia["estado"],
            "evidencia": proveniencia["evidencia"],
        }
        if proveniencia["estado"] == AUSENTE_COMPROVADO_NO_DOCUMENTO:
            pendencias.append(item)
        else:
            bloqueantes.append(item)
    return pendencias, bloqueantes
