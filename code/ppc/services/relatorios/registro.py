from dataclasses import dataclass
from typing import Callable

RELATORIOS = {}


@dataclass(frozen=True)
class Relatorio:
    chave: str
    titulo: str
    grupo: str
    descricao: str
    filtros: tuple        # "periodo" e/ou "curso"
    funcao: Callable      # recebe cleaned_data do formulário -> {"colunas", "linhas", "resumo"}


def relatorio(chave, titulo, grupo, descricao, filtros=()):
    def decorador(funcao):
        if chave in RELATORIOS:
            raise ValueError(f"Relatório duplicado: {chave}")
        RELATORIOS[chave] = Relatorio(chave, titulo, grupo, descricao, tuple(filtros), funcao)
        return funcao
    return decorador


def agrupados():
    grupos = {}
    for r in RELATORIOS.values():
        grupos.setdefault(r.grupo, []).append(r)
    return grupos