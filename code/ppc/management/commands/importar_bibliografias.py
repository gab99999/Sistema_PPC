import csv
import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from simple_history.utils import bulk_create_with_history

from ppc.models import ReferenciaBibliografica


class Command(BaseCommand):
    help = "Importa referências bibliográficas de um arquivo CSV."

    def add_arguments(self, parser):
        parser.add_argument(
            "arquivo",
            type=str,
            help="Caminho do arquivo bibliografias_limpas.csv",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=2000,
            help="Quantidade de registros por lote (padrão: 2000).",
        )

    def handle(self, *args, **options):
        caminho = Path(options["arquivo"]).expanduser()
        batch_size = options["batch_size"]

        if not caminho.is_file():
            raise CommandError(f"Arquivo não encontrado: {caminho}")

        if batch_size < 1:
            raise CommandError("O batch-size deve ser maior que zero.")

        colunas_obrigatorias = {
            "titulo",
            "autores",
            "editora",
            "cidade",
            "ano",
        }

        processados = 0
        inseridos = 0
        ignorados = 0
        lote = []

        def texto_limitado(valor, tamanho):
            """Converte para string, remove espaços externos e trunca."""
            return str(valor or "").strip()[:tamanho]

        def converter_ano(valor):
            """Converte um ano de quatro dígitos em int; inválidos viram None."""
            valor = str(valor or "").strip()

            if re.fullmatch(r"\d{4}", valor):
                return int(valor)

            return None

        self.stdout.write(f"Iniciando importação: {caminho}")
        self.stdout.write(f"Tamanho dos lotes: {batch_size}")

        try:
            with caminho.open(
                mode="r",
                encoding="utf-8-sig",
                newline="",
            ) as arquivo:
                leitor = csv.DictReader(
                    arquivo,
                    delimiter=";",
                    quotechar='"',
                )

                if not leitor.fieldnames:
                    raise CommandError("O CSV está vazio ou não possui cabeçalho.")

                # Normaliza os nomes das colunas.
                leitor.fieldnames = [
                    (coluna or "").strip().lower()
                    for coluna in leitor.fieldnames
                ]

                colunas_ausentes = colunas_obrigatorias - set(leitor.fieldnames)

                if colunas_ausentes:
                    raise CommandError(
                        "Colunas ausentes no CSV: "
                        + ", ".join(sorted(colunas_ausentes))
                    )

                # Garante que qualquer falha durante a importação reverta
                # os lotes já processados.
                with transaction.atomic():
                    for linha in leitor:
                        processados += 1

                        titulo = texto_limitado(linha.get("titulo"), 300)

                        # O título é obrigatório para a referência.
                        if not titulo:
                            ignorados += 1
                            continue

                        autores = texto_limitado(linha.get("autores"), 300)
                        editora = texto_limitado(linha.get("editora"), 150)
                        cidade = texto_limitado(linha.get("cidade"), 100)
                        ano = converter_ano(linha.get("ano"))

                        referencia = ReferenciaBibliografica(
                            titulo=titulo,
                            autores=autores,
                            editora=editora,
                            cidade=cidade,
                            ano=ano,
                        )

                        # Registra o motivo no histórico, além de inserir
                        # os dados em lote.
                        referencia._change_reason = (
                            "Importação inicial de bibliografias via CSV"
                        )

                        lote.append(referencia)

                        if len(lote) >= batch_size:
                            quantidade_lote = len(lote)

                            bulk_create_with_history(
                                lote,
                                ReferenciaBibliografica,
                                batch_size=batch_size,
                                default_change_reason=(
                                    "Importação inicial de bibliografias via CSV"
                                ),
                            )

                            inseridos += quantidade_lote
                            lote.clear()

                            self.stdout.write(
                                f"Processados: {processados} | "
                                f"Inseridos: {inseridos} | "
                                f"Ignorados: {ignorados}"
                            )

                    # Insere o lote final, caso esteja incompleto.
                    if lote:
                        quantidade_lote = len(lote)

                        bulk_create_with_history(
                            lote,
                            ReferenciaBibliografica,
                            batch_size=batch_size,
                            default_change_reason=(
                                "Importação inicial de bibliografias via CSV"
                            ),
                        )

                        inseridos += quantidade_lote
                        lote.clear()

        except (OSError, UnicodeDecodeError, csv.Error) as exc:
            raise CommandError(f"Erro ao ler o CSV: {exc}") from exc

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Importação concluída!"))
        self.stdout.write(f"Registros processados: {processados}")
        self.stdout.write(
            self.style.SUCCESS(f"Registros inseridos: {inseridos}")
        )
        self.stdout.write(f"Registros ignorados por título vazio: {ignorados}")