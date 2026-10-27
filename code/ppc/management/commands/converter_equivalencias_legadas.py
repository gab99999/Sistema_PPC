"""Converte grupos antigos sem removê-los; por padrão, apenas simula."""
from django.core.management.base import BaseCommand
from ppc.models import EquivalenciaMatriz, ItemEquivalencia


class Command(BaseCommand):
    help = "Simula ou converte grupos legados para pares entre edições explícitas."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Simula; também é o comportamento padrão.")
        parser.add_argument("--aplicar", action="store_true", help="Grava pares válidos; mantém grupos legados.")

    def handle(self, *args, **options):
        aplicar = options["aplicar"]
        criados = ignorados = 0
        for grupo_id in ItemEquivalencia.objects.order_by().values_list("grupo_id", flat=True).distinct():
            itens = list(ItemEquivalencia.objects.filter(grupo_id=grupo_id).select_related(
                "item_matriz__matriz__curso", "item_matriz__matriz__matriz_anterior", "item_matriz__componente"
            ).order_by("ordem", "pk"))
            for pos, novo in enumerate(itens[1:], start=1):
                for antigo in itens[:pos]:
                    n, a = novo.item_matriz, antigo.item_matriz
                    motivo = ""
                    if not n.matriz.curso_id or n.matriz.curso_id != a.matriz.curso_id:
                        motivo = "matrizes sem o mesmo curso vinculado"
                    elif n.matriz_id == a.matriz_id:
                        motivo = "grupo contém itens da mesma matriz"
                    else:
                        cursor = n.matriz.matriz_anterior
                        ancestrais = set()
                        while cursor and cursor.pk not in ancestrais:
                            ancestrais.add(cursor.pk)
                            cursor = cursor.matriz_anterior
                        if a.matriz_id not in ancestrais:
                            motivo = "matriz anterior não está na linhagem explícita"
                        else:
                            try:
                                ch_antiga = a.componente.carga_horaria_computada_total
                                ch_nova = n.componente.carga_horaria_computada_total
                            except (TypeError, ValueError):
                                motivo = "carga horária inválida em dado legado"
                            if not motivo and ch_antiga < ch_nova:
                                motivo = "CH da matriz anterior menor que a CH nova"
                    if motivo:
                        ignorados += 1
                        self.stdout.write(f"IGNORADO grupo={grupo_id} novo={n.pk} anterior={a.pk}: {motivo}")
                        continue
                    existe = EquivalenciaMatriz.objects.filter(item_novo=n, item_anterior=a).exists()
                    if aplicar and not existe:
                        EquivalenciaMatriz.objects.create(item_novo=n, item_anterior=a)
                    if not existe:
                        criados += 1
        acao = "Gravados" if aplicar else "Simulação; seriam gravados"
        self.stdout.write(self.style.SUCCESS(f"{acao}: {criados} pares. Ignorados: {ignorados}. Grupos e itens legados preservados."))
