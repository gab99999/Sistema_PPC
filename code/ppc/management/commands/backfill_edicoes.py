from django.core.management.base import BaseCommand, CommandError
from django.db.models import Min
from django.utils import timezone

from ppc.models import EventoEdicao
from ppc.services.auditoria import montar_evento, registro_edicao


class Command(BaseCommand):
    help = "Preenche EventoEdicao a partir do histórico (simple_history)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--modelo", action="append", help="app.Modelo; repita para vários. Padrão: todos.")

    def handle(self, *args, **opts):
        modelos = list(registro_edicao())
        if opts["modelo"]:
            pedidos = {p.lower() for p in opts["modelo"]}
            modelos = [m for m in modelos if m._meta.label_lower in pedidos]
            if not modelos:
                raise CommandError("Nenhum modelo rastreado corresponde a --modelo.")
        agora = timezone.now()
        total = 0
        for modelo in modelos:
            limite = (EventoEdicao.objects.filter(modelo=modelo._meta.label)
                      .aggregate(m=Min("ocorreu_em"))["m"] or agora)
            ultimo, lote = {}, []
            qs = modelo.history.model.objects.filter(history_date__lt=limite).order_by("history_date", "history_id")
            for h in qs.iterator(chunk_size=2000):
                anterior = ultimo.get(h.id)
                ultimo[h.id] = h
                ev = montar_evento(modelo, h, anterior)
                if ev:
                    lote.append(ev)
            self.stdout.write(f"{modelo._meta.label}: {len(lote)} eventos")
            total += len(lote)
            if not opts["dry_run"]:
                EventoEdicao.objects.bulk_create(lote, batch_size=500, ignore_conflicts=True)
        self.stdout.write(self.style.SUCCESS(f"Total: {total}" + (" (dry-run)" if opts["dry_run"] else "")))