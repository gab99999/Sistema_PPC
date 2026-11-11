import csv
import re
import time
import unicodedata
from collections import Counter
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from simple_history.utils import bulk_create_with_history

from ppc.models import ReferenciaBibliografica


MOTIVO_HISTORICO = "Importação de bibliografias via CSV"
TAMANHOS_CAMPOS = {
    "titulo": 300,
    "autores": 300,
    "editora": 150,
    "cidade": 100,
}
CAMPOS_CHAVE = ("titulo", "autores", "editora", "cidade", "ano")


def _texto_limitado(valor, tamanho):
    return str(valor or "").strip()[:tamanho]


def _converter_ano(valor):
    valor = str(valor or "").strip()
    return int(valor) if re.fullmatch(r"\d{4}", valor) else None


def _normalizar_texto(valor, *, ignorar_acentos):
    texto = " ".join(str(valor or "").split())
    texto = unicodedata.normalize("NFC", texto).casefold()
    if ignorar_acentos:
        texto = "".join(
            caractere
            for caractere in unicodedata.normalize("NFD", texto)
            if unicodedata.category(caractere) != "Mn"
        )
        texto = unicodedata.normalize("NFC", texto)
    return texto


def _chave(dados, *, ignorar_acentos=True):
    return tuple(
        _normalizar_texto(dados.get(campo), ignorar_acentos=ignorar_acentos)
        if campo != "ano" else dados.get("ano")
        for campo in CAMPOS_CHAVE
    )


class Command(BaseCommand):
    help = "Importa referências bibliográficas de um arquivo CSV (simulação por padrão)."

    def add_arguments(self, parser):
        parser.add_argument("arquivo", type=str, help="Caminho do arquivo bibliografias_limpas.csv")
        parser.add_argument("--batch-size", type=int, default=2000)
        parser.add_argument(
            "--confirmar", action="store_true",
            help="Grava as novas referências; sem esta opção apenas simula.",
        )

    def handle(self, *args, **options):
        inicio = time.monotonic()
        caminho = Path(options["arquivo"]).expanduser()
        batch_size = options["batch_size"]
        confirmar = options["confirmar"]
        if not caminho.is_file():
            raise CommandError(f"Arquivo não encontrado: {caminho}")
        if batch_size < 1:
            raise CommandError("O batch-size deve ser maior que zero.")

        obrigatorias = set(CAMPOS_CHAVE)
        linhas_lidas = linhas_ignoradas = anos_none = repetidas_arquivo = 0
        distinct_file = {}
        vistos_sem_acentos = {}
        exemplos_acentos = []
        catalogo_contagens = Counter()
        catalogo_chaves = set()
        novas = []
        gravadas = lotes_gravados = 0

        try:
            # Seleciona somente os campos da chave; ordenar por PK fixa qual
            # registro legado representa primeiro uma chave já repetida.
            existentes = ReferenciaBibliografica.objects.order_by("pk").values_list(*CAMPOS_CHAVE)
            for valores in existentes.iterator(chunk_size=2000):
                dados = dict(zip(CAMPOS_CHAVE, valores))
                chave = _chave(dados)
                catalogo_contagens[chave] += 1
                catalogo_chaves.add(chave)
            grupos_duplicados_catalogo = sum(1 for total in catalogo_contagens.values() if total > 1)

            with caminho.open(mode="r", encoding="utf-8-sig", newline="") as arquivo:
                leitor = csv.DictReader(arquivo, delimiter=";", quotechar='"')
                if not leitor.fieldnames:
                    raise CommandError("O CSV está vazio ou não possui cabeçalho.")
                leitor.fieldnames = [(coluna or "").strip().lower() for coluna in leitor.fieldnames]
                ausentes = obrigatorias - set(leitor.fieldnames)
                if ausentes:
                    raise CommandError("Colunas ausentes no CSV: " + ", ".join(sorted(ausentes)))

                for numero_linha, linha in enumerate(leitor, start=2):
                    linhas_lidas += 1
                    dados = {
                        campo: _texto_limitado(linha.get(campo), limite)
                        for campo, limite in TAMANHOS_CAMPOS.items()
                    }
                    valor_ano = str(linha.get("ano") or "").strip()
                    dados["ano"] = _converter_ano(valor_ano)
                    if dados["ano"] is None:
                        anos_none += 1
                    if not dados["titulo"]:
                        linhas_ignoradas += 1
                        continue

                    chave = _chave(dados)
                    chave_com_acentos = _chave(dados, ignorar_acentos=False)
                    chave_sem_acentos = _chave(dados)
                    if chave in distinct_file:
                        repetidas_arquivo += 1
                        primeira = distinct_file[chave]
                        chave_primeira_com_acentos = _chave(primeira["dados"], ignorar_acentos=False)
                        if (
                            chave_primeira_com_acentos != chave_com_acentos
                            and len(exemplos_acentos) < 10
                            and not any(exemplo["chave"] == chave_sem_acentos for exemplo in exemplos_acentos)
                        ):
                            exemplos_acentos.append({
                                "chave": chave_sem_acentos,
                                "linha_a": primeira["linha"], "titulo_a": primeira["dados"]["titulo"],
                                "linha_b": numero_linha, "titulo_b": dados["titulo"],
                            })
                        continue

                    distinct_file[chave] = {"linha": numero_linha, "dados": dados}
                    if chave in catalogo_chaves:
                        continue

                    referencia = ReferenciaBibliografica(**dados)
                    referencia._change_reason = MOTIVO_HISTORICO
                    novas.append(referencia)
                    # Evita repetir uma chave ainda aguardando fechamento do lote.
                    catalogo_chaves.add(chave)

                    if confirmar and len(novas) >= batch_size:
                        quantidade = len(novas)
                        with transaction.atomic():
                            bulk_create_with_history(
                                novas, ReferenciaBibliografica, batch_size=batch_size,
                                default_change_reason=MOTIVO_HISTORICO,
                            )
                        gravadas += quantidade
                        lotes_gravados += 1
                        novas.clear()

            if confirmar and novas:
                quantidade = len(novas)
                with transaction.atomic():
                    bulk_create_with_history(
                        novas, ReferenciaBibliografica, batch_size=batch_size,
                        default_change_reason=MOTIVO_HISTORICO,
                    )
                gravadas += quantidade
                lotes_gravados += 1
                novas.clear()
        except Exception as exc:
            duracao = time.monotonic() - inicio
            self._relatorio(
                confirmar=confirmar, linhas_lidas=linhas_lidas,
                linhas_ignoradas=linhas_ignoradas, anos_none=anos_none,
                repetidas_arquivo=repetidas_arquivo,
                distintas=len(distinct_file), existentes=sum(1 for chave in distinct_file if chave in catalogo_contagens),
                novas=len(distinct_file) - sum(1 for chave in distinct_file if chave in catalogo_contagens),
                gravadas=gravadas, lotes= lotes_gravados,
                grupos_duplicados_catalogo=sum(1 for total in catalogo_contagens.values() if total > 1),
                exemplos=exemplos_acentos, duracao=duracao,
            )
            if confirmar:
                self.stderr.write(
                    self.style.ERROR(
                        f"Falha: {exc}. Foram concluídos {lotes_gravados} lote(s), "
                        f"com {gravadas} obra(s) gravada(s). Repita com --confirmar; "
                        "as obras já registradas serão puladas. Não considere a execução concluída."
                    )
                )
            if isinstance(exc, CommandError):
                raise
            raise CommandError(str(exc)) from exc

        duracao = time.monotonic() - inicio
        existentes_arquivo = sum(1 for chave in distinct_file if chave in catalogo_contagens)
        novas_calculadas = len(distinct_file) - existentes_arquivo
        self._relatorio(
            confirmar=confirmar, linhas_lidas=linhas_lidas,
            linhas_ignoradas=linhas_ignoradas, anos_none=anos_none,
            repetidas_arquivo=repetidas_arquivo, distintas=len(distinct_file),
            existentes=existentes_arquivo, novas=novas_calculadas,
            gravadas=gravadas, lotes=lotes_gravados,
            grupos_duplicados_catalogo=grupos_duplicados_catalogo,
            exemplos=exemplos_acentos, duracao=duracao,
        )
        if confirmar:
            self.stdout.write(self.style.SUCCESS("Importação concluída."))
        else:
            self.stdout.write(self.style.WARNING("Simulação concluída; nada foi gravado."))

    def _relatorio(
        self, *, confirmar, linhas_lidas, linhas_ignoradas, anos_none,
        repetidas_arquivo, distintas, existentes, novas, gravadas, lotes,
        grupos_duplicados_catalogo, exemplos, duracao,
    ):
        self.stdout.write(f"Linhas lidas: {linhas_lidas}")
        self.stdout.write(f"Linhas ignoradas (título vazio): {linhas_ignoradas}")
        self.stdout.write(f"Linhas com ano convertido para None: {anos_none}")
        self.stdout.write(f"Linhas repetidas dentro do arquivo: {repetidas_arquivo}")
        self.stdout.write(f"Obras distintas no arquivo: {distintas}")
        self.stdout.write(f"Já existentes no catálogo: {existentes}")
        self.stdout.write(f"Novas a criar: {novas}")
        if confirmar:
            self.stdout.write(f"Obras criadas: {gravadas}")
            self.stdout.write(f"Lotes gravados: {lotes}")
        self.stdout.write(
            f"Grupos repetidos no catálogo existente (informativo): {grupos_duplicados_catalogo}"
        )
        if exemplos:
            self.stdout.write("Exemplos unidos apenas por diferença de acento (linha: título):")
            for exemplo in exemplos:
                self.stdout.write(
                    f"  {exemplo['linha_a']}: {exemplo['titulo_a']}  |  "
                    f"{exemplo['linha_b']}: {exemplo['titulo_b']}"
                )
        self.stdout.write(f"Duração: {duracao:.3f} segundo(s)")
