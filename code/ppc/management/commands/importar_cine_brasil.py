# ppc/management/commands/importar_cine_brasil.py
import csv
from django.core.management.base import BaseCommand
from ppc.models import CineBrasilCurso

class Command(BaseCommand):
    help = "Importa CineBrasilCurso a partir de um CSV gerado pela análise do documento INEP."

    def add_arguments(self, parser):
        parser.add_argument('caminho_csv', type=str)

    def handle(self, *args, **options):
        criados, ja_existentes = 0, 0
        with open(options['caminho_csv'], encoding='utf-8') as arquivo:
            for linha in csv.DictReader(arquivo):
                _, foi_criado = CineBrasilCurso.objects.get_or_create(
                    nome_curso=linha['nome_curso'],
                    area_geral_codigo=linha['area_geral_codigo'],
                    rotulo_codigo=linha['rotulo_codigo'],
                    defaults={
                        'area_geral_nome': linha['area_geral_nome'],
                        'rotulo_nome': linha['rotulo_nome'],
                        'origem': linha.get('origem', ''),
                    },
                )
                criados += foi_criado
                ja_existentes += not foi_criado
        self.stdout.write(self.style.SUCCESS(f"{criados} criados, {ja_existentes} já existentes."))