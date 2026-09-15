
from django.core.management.base import BaseCommand
from ppc.models import MapeamentoImportacaoMatriz
from ppc.services.normalizacao_componentes import normalizar_planilha_matriz


class Command(BaseCommand):
    help = (
        "Lista todos os identificador_origem distintos da planilha, indicando "
        "quais já têm mapeamento para um Curso e quais ainda faltam."
    )

    def add_arguments(self, parser):
        parser.add_argument("caminho_arquivo", type=str)

    def handle(self, *args, **options):
        caminho = options["caminho_arquivo"]

        self.stdout.write("Lendo planilha...")
        linhas = normalizar_planilha_matriz(caminho)

        # conta quantas linhas cada identificador tem, pra dar noção de tamanho
        contagem = {}
        for linha in linhas:
            origem = linha["identificador_origem"]
            contagem[origem] = contagem.get(origem, 0) + 1

        mapeados = set(
            MapeamentoImportacaoMatriz.objects.values_list("identificador_origem", flat=True)
        )

        identificadores = sorted(contagem.keys())
        faltando = [i for i in identificadores if i not in mapeados]

        self.stdout.write(
            f"\nTotal de identificadores distintos: {len(identificadores)}"
        )
        self.stdout.write(
            f"Já mapeados: {len(mapeados)}"
        )
        self.stdout.write(
            self.style.WARNING(f"Faltando mapear: {len(faltando)}\n")
        )

        if faltando:
            self.stdout.write("Identificadores sem mapeamento (identificador — nº de linhas):")
            for origem in faltando:
                self.stdout.write(f"  {origem} — {contagem[origem]} linha(s)")