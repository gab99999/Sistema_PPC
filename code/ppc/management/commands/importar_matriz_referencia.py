# ppc/management/commands/importar_matriz_referencia.py
from django.core.management.base import BaseCommand
from ppc.services.normalizacao_componentes import normalizar_planilha_matriz
from ppc.services.importacao_matriz_referencia import importar_linhas_normalizadas


class Command(BaseCommand):
    help = "Importa a planilha institucional de componentes/matrizes de referência."

    def add_arguments(self, parser):
        parser.add_argument("caminho_arquivo", type=str)
        parser.add_argument(
            "--confirmar",
            action="store_true",
            help="Sem essa flag, roda em modo dry-run (só mostra o relatório, não grava nada).",
        )

    def handle(self, *args, **options):
        caminho = options["caminho_arquivo"]
        dry_run = not options["confirmar"]

        self.stdout.write("Lendo e normalizando planilha...")
        linhas = normalizar_planilha_matriz(caminho)
        self.stdout.write(f"{len(linhas)} linhas lidas.\n")

        relatorio = importar_linhas_normalizadas(linhas, dry_run=dry_run)

        self.stdout.write(self.style.SUCCESS(f"OK (prontas/gravadas): {len(relatorio['ok'])}"))
        self.stdout.write(self.style.WARNING(f"Pendentes de revisão (ambíguas): {len(relatorio['pendentes_revisao'])}"))
        self.stdout.write(f"Duplicadas idênticas (ignoradas): {len(relatorio['duplicadas_identicas'])}")
        self.stdout.write(self.style.ERROR(f"Duplicadas conflitantes (não gravadas): {len(relatorio['duplicadas_conflitantes'])}"))
        self.stdout.write(self.style.ERROR(f"Sem mapeamento de curso (não gravadas): {len(relatorio['sem_mapeamento'])}"))

        if relatorio["erros"]:
            self.stdout.write(self.style.ERROR(f"Erros inesperados: {len(relatorio['erros'])}"))
            for e in relatorio["erros"][:10]:
                self.stdout.write(f"  linha {e['linha']['linha_origem']}: {e['erro']}")
        if relatorio["pendentes_revisao"] or relatorio["duplicadas_conflitantes"] or relatorio["sem_mapeamento"]:
            self.stdout.write(
                "\nPendências gravadas em Pendências de Importação (admin) para revisão."
            )

        if dry_run:
            self.stdout.write(self.style.WARNING(
                "\nModo dry-run — nada foi gravado. Rode novamente com --confirmar para gravar."
            ))
        else:
            self.stdout.write(self.style.SUCCESS("\nImportação concluída e gravada no banco."))