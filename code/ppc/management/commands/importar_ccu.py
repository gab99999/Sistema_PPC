
from pathlib import Path

import openpyxl
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from ppc.models import ComponenteCurricular


class Command(BaseCommand):
    help = "Importa códigos de um Excel e marca componentes como CCU."

    def add_arguments(self, parser):
        parser.add_argument(
            "arquivo",
            type=str,
            help="Caminho do arquivo Excel (.xlsx)",
        )

    def handle(self, *args, **options):
        caminho = Path(options["arquivo"])

        if not caminho.is_file():
            raise CommandError(f"Arquivo não encontrado: {caminho}")

        try:
            workbook = openpyxl.load_workbook(
                caminho,
                read_only=True,
                data_only=True,
            )
        except Exception as exc:
            raise CommandError(f"Erro ao abrir o Excel: {exc}")

        codigos = []

        try:
            planilha = workbook.active

            # Lê a coluna B, ignorando células vazias e o cabeçalho.
            for (valor,) in planilha.iter_rows(
                min_col=2,
                max_col=2,
                values_only=True,
            ):
                if valor is None:
                    continue

                codigo = str(valor).strip()

                if not codigo or codigo.lower() == "código do ccu":
                    continue

                codigos.append(codigo)
        finally:
            workbook.close()

        codigos_nao_encontrados = []
        componentes_marcados = 0

        with transaction.atomic():
            for codigo in dict.fromkeys(codigos):
                componentes = ComponenteCurricular.objects.filter(
                    codigo=codigo
                )

                if not componentes.exists():
                    codigos_nao_encontrados.append(codigo)
                    continue

                # Atualiza todos os componentes com esse código exato.
                # Não salva novamente os que já são CCU.
                for componente in componentes:
                    if componente.ccu is not True:
                        componente.ccu = True
                        componente.save(update_fields=["ccu"])
                        componentes_marcados += 1

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Importação concluída!"))
        self.stdout.write(
            f"Componentes marcados como CCU: {componentes_marcados}"
        )
        self.stdout.write(
            f"Códigos não encontrados: {len(codigos_nao_encontrados)}"
        )

        if codigos_nao_encontrados:
            self.stdout.write("\nLista de códigos não encontrados:")

            for codigo in codigos_nao_encontrados:
                self.stdout.write(f"- {codigo}")
        else:
            self.stdout.write(
                self.style.SUCCESS("Todos os códigos foram encontrados.")
            )
