import re
import unicodedata

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from ppc.models import Bibliografia, BibliografiaReferencia, ReferenciaBibliografica
from ppc.services.eventos import registrar_evento, suspender_eventos_edicao


def normalizar_texto(valor):
    texto = unicodedata.normalize("NFKD", valor or "")
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return " ".join(re.findall(r"[a-z0-9]+", texto.casefold()))


class Command(BaseCommand):
    help = "Reconcilia bibliografias legadas com o catálogo da Biblioteca por título, autores e ano."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Exibe o relatório sem alterar o banco (comportamento padrão).",
        )
        parser.add_argument(
            "--confirmar", action="store_true",
            help="Vincula somente correspondências únicas, sem alterar os textos existentes.",
        )

    def handle(self, *args, **options):
        if options["dry_run"] and options["confirmar"]:
            raise CommandError("Use --dry-run ou --confirmar, não ambos.")
        dry_run = not options["confirmar"]

        indice = {}
        for ref in ReferenciaBibliografica.objects.only("id", "titulo", "autores", "ano").iterator(chunk_size=2000):
            chave = (normalizar_texto(ref.titulo), normalizar_texto(ref.autores))
            indice.setdefault(chave, []).append((ref.id, ref.ano))

        vinculadas = 0
        sem_correspondencia = []
        ambiguas = []
        duplicatas = []
        pendentes = []
        for modelo in (Bibliografia, BibliografiaReferencia):
            campo_item = "componente_na_matriz_id" if modelo is Bibliografia else "componente_na_matriz_referencia_id"
            ids_referencias = {ref_id for refs in indice.values() for ref_id, _ in refs}
            pares_existentes = set(modelo.objects.filter(
                referencia_id__in=ids_referencias,
            ).values_list(campo_item, "referencia_id"))
            pares_planejados = set()
            qs = modelo.objects.filter(referencia__isnull=True).select_related(
                "componente_na_matriz__componente" if modelo is Bibliografia
                else "componente_na_matriz_referencia__componente"
            )
            if modelo is Bibliografia:
                qs = qs.select_related("componente_na_matriz__ppc__curso")
            else:
                qs = qs.select_related("componente_na_matriz_referencia__matriz")
            for bib in qs.iterator(chunk_size=1000):
                chave = (normalizar_texto(bib.titulo), normalizar_texto(bib.autores))
                candidatos = indice.get(chave, [])
                if bib.ano is not None:
                    candidatos = [c for c in candidatos if c[1] == bib.ano]
                identificador = f"{modelo.__name__} #{bib.pk}: {bib.titulo!r} — {bib.autores!r} ({bib.ano or 'sem ano'})"
                if not candidatos:
                    sem_correspondencia.append(identificador)
                    continue
                if len(candidatos) != 1:
                    ambiguas.append(f"{identificador} — {len(candidatos)} correspondências")
                    continue
                ref_id = candidatos[0][0]
                par = (getattr(bib, campo_item), ref_id)
                if par in pares_existentes or par in pares_planejados:
                    duplicatas.append(f"{identificador} — obra já vinculada ao componente")
                    continue
                pares_planejados.add(par)
                pendentes.append((bib, ref_id))

        if not dry_run:
            with transaction.atomic(), suspender_eventos_edicao():
                for bib, ref_id in pendentes:
                    bib.referencia_id = ref_id
                    bib.save(update_fields=["referencia"])
                    vinculadas += 1
            registrar_evento(
                "bibliografias_reconciliadas", identificador="reconciliar_bibliografias",
                vinculadas=vinculadas, ambiguas=len(ambiguas), sem_correspondencia=len(sem_correspondencia),
            )

        self.stdout.write(f"Modo: {'dry-run' if dry_run else 'gravação'}")
        self.stdout.write(f"Correspondências únicas: {len(pendentes)}" + (" (não gravadas)" if dry_run else f" (vinculadas: {vinculadas})"))
        self.stdout.write(f"Sem correspondência: {len(sem_correspondencia)}")
        for linha in sem_correspondencia:
            self.stdout.write(f"  SEM CORRESPONDÊNCIA — {linha}")
        self.stdout.write(f"Ambíguas: {len(ambiguas)}")
        for linha in ambiguas:
            self.stdout.write(f"  AMBÍGUA — {linha}")
        self.stdout.write(f"Duplicatas no componente: {len(duplicatas)}")
        for linha in duplicatas:
            self.stdout.write(f"  DUPLICATA NO COMPONENTE — {linha}")

