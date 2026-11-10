from django.db import transaction

from ppc.models import (
    BibliografiaReferencia,
    ComponenteNaMatrizReferencia,
    MatrizReferenciaCurricular,
)
from ppc.services.eventos import suspender_eventos_edicao
from .fluxograma import copiar_relacoes_entre_matrizes


def copiar_matriz_referencia(origem, *, nome, curso, numero_periodos=None, nova_edicao=False):
    """Cria uma matriz EM MUDANÇA copiando vínculos, bibliografias e relações da origem.
    Retorna (copia, total_itens, relacoes_ignoradas)."""
    with transaction.atomic():
        copia = MatrizReferenciaCurricular.objects.create(
            curso=curso,
            nome=nome,
            numero_periodos=numero_periodos or origem.numero_periodos,
            grau_academico=origem.grau_academico,
            matriz_anterior=origem if nova_edicao else None,
            status=MatrizReferenciaCurricular.STATUS_EM_MUDANCA,
        )
        total_itens = 0
        # create() (e não bulk_create) para gravar o history de cada item;
        # o EventoEdicao por item fica suspenso.
        with suspender_eventos_edicao():
            for item in origem.componentes.all():
                novo_item = ComponenteNaMatrizReferencia.objects.create(
                    matriz=copia, componente_id=item.componente_id,
                    periodo=item.periodo, natureza=item.natureza, ordem=item.ordem,
                    nucleo=item.nucleo, grupo_licenciatura=item.grupo_licenciatura,
                )
                total_itens += 1
                for bib in item.bibliografias.all():
                    BibliografiaReferencia.objects.create(
                        componente_na_matriz_referencia=novo_item,
                        referencia_id=bib.referencia_id, tipo=bib.tipo,
                        titulo=bib.titulo, autores=bib.autores,
                        editora=bib.editora, cidade=bib.cidade, ano=bib.ano,
                    )
            relacoes_ignoradas = copiar_relacoes_entre_matrizes(origem, copia)
    return copia, total_itens, relacoes_ignoradas