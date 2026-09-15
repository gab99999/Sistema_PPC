# ppc/management/commands/popular_mapeamento_pendentes.py
from django.core.management.base import BaseCommand
from ppc.models import MapeamentoImportacaoMatriz
from ppc.services.normalizacao_componentes import normalizar_planilha_matriz


class Command(BaseCommand):
    help = (
        "Cria em MapeamentoImportacaoMatriz uma linha (com curso em branco) para "
        "cada identificador_origem da planilha que ainda não tem mapeamento. "
        "Não define curso automaticamente — isso precisa ser preenchido manualmente "
        "no admin, um por um."
    )

    def add_arguments(self, parser):
        parser.add_argument("caminho_arquivo", type=str)

    def handle(self, *args, **options):
        caminho = options["caminho_arquivo"]

        self.stdout.write("Lendo planilha...")
        linhas = normalizar_planilha_matriz(caminho)

        contagem = {}
        for linha in linhas:
            origem = linha["identificador_origem"]
            contagem[origem] = contagem.get(origem, 0) + 1

        ja_existentes = set(
            MapeamentoImportacaoMatriz.objects.values_list("identificador_origem", flat=True)
        )

        faltando = sorted(set(contagem.keys()) - ja_existentes)

        if not faltando:
            self.stdout.write(self.style.SUCCESS("Nenhum identificador pendente de criação."))
            return

        novos = [
            MapeamentoImportacaoMatriz(
                identificador_origem=origem,
                curso=None,
                observacao=f"{contagem[origem]} linha(s) na planilha — curso ainda não definido.",
            )
            for origem in faltando
        ]

        MapeamentoImportacaoMatriz.objects.bulk_create(novos)

        self.stdout.write(
            self.style.SUCCESS(
                f"{len(novos)} identificador(es) criado(s) em Mapeamento Importação Matriz, "
                f"com curso em branco. Preencha o curso de cada um no admin."
            )
        )