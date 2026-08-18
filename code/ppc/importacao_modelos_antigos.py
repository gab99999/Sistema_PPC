"""Ponte entre o pipeline adaptativo e o fluxo Django de revisão de PPC."""

from __future__ import annotations

from typing import Any

from ppc.testes.analisar_pdf_uma_chamada import analisar_pdf_adaptativo, validar_pre_save_django


class ErroImportacaoPPC(RuntimeError):
    """Erro seguro para apresentação ao usuário, com causa preservada em log."""


def preparar_importacao_modelo_antigo(arquivo: Any) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Executa extração e validação sem criar ou alterar registros no banco."""
    try:
        dados, diagnostico = analisar_pdf_adaptativo(arquivo)
        pre_save = validar_pre_save_django(dados)
        return dados, pre_save, diagnostico.como_dict()
    except (ValueError, OSError, RuntimeError) as erro:
        raise ErroImportacaoPPC(str(erro)) from erro
