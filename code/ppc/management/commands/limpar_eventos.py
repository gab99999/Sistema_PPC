from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from ppc.models import EventoUso, UsoDiario


class Command(BaseCommand):
    help = "Apaga logs de acesso e uso mais antigos que N meses (padrão 12). Eventos de edição e de negócio ficam."

    def add_arguments(self, parser):
        parser.add_argument("--meses", type=int, default=12)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        dias = 30 * opts["meses"]
        acessos = EventoUso.objects.filter(
            tipo__in=EventoUso.TIPOS_ACESSO, criado_em__lt=timezone.now() - timedelta(days=dias)
        )
        usos = UsoDiario.objects.filter(data__lt=timezone.localdate() - timedelta(days=dias))
        self.stdout.write(f"Acessos: {acessos.count()} | Usos diários: {usos.count()}")
        if not opts["dry_run"]:
            acessos.delete()
            usos.delete()
            self.stdout.write(self.style.SUCCESS("Apagado."))