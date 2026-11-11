import contextlib
import hashlib
import io
import logging
import os
import secrets
import tempfile
import time
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.utils import timezone

from ppc.models import EventoUso
from ppc.services.eventos import registrar_evento

logger = logging.getLogger(__name__)

LIMITE_SAIDA = 12000
TEMPO_TOKEN_MINUTOS = 30
CHAVE_SESSAO_IMPORTACAO = "ppc_importacao_pendente"

IMPORTACOES = {
    "importar_matriz_referencia": {
        "rotulo": "Matriz de referência",
        "ajuda": "Planilha institucional de componentes e matrizes curriculares.",
        "extensoes": (".xlsx",),
        "dry_run": True,
        "disponivel": True,
        "argumentos": {},
    },
    "importar_ccu": {
        "rotulo": "Códigos CCU",
        "ajuda": "Planilha Excel com os códigos CCU na coluna B.",
        "extensoes": (".xlsx",),
        "dry_run": False,
        "disponivel": True,
        "argumentos": {},
    },
    "importar_bibliografias": {
        "rotulo": "Bibliografias",
        "ajuda": "CSV bibliográfico. Se a página expirar durante a confirmação, envie o mesmo arquivo, simule e confirme novamente; obras já gravadas serão ignoradas.",
        "extensoes": (".csv",),
        "dry_run": True,
        "disponivel": True,
        "argumentos": {},
    },
    "importar_cine_brasil": {
        "rotulo": "Cine Brasil",
        "ajuda": "CSV de cursos, áreas gerais e rótulos Cine Brasil.",
        "extensoes": (".csv",),
        "dry_run": False,
        "disponivel": True,
        "argumentos": {},
    },
}


def tamanho_maximo_bytes():
    return int(getattr(settings, "IMPORTACAO_TAMANHO_MAXIMO_MB", 10)) * 1024 * 1024


def calcular_sha256(caminho):
    digest = hashlib.sha256()
    with open(caminho, "rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
            digest.update(bloco)
    return digest.hexdigest()


def localizar_importacao(comando):
    return IMPORTACOES.get(comando)


def lista_importacoes():
    return [{"comando": comando, **registro} for comando, registro in IMPORTACOES.items()]


def salvar_temporario(upload, extensao):
    """Copia upload validado para um nome aleatório fora do projeto e de MEDIA_ROOT."""
    diretorio = Path(tempfile.gettempdir()).resolve()
    projeto = Path(settings.BASE_DIR).resolve()
    media = Path(settings.MEDIA_ROOT).resolve()
    if diretorio == projeto or projeto in diretorio.parents or diretorio == media or media in diretorio.parents:
        raise OSError("O diretório temporário configurado fica dentro do projeto ou de MEDIA_ROOT.")

    descritor, nome = tempfile.mkstemp(prefix="ppc-importacao-", suffix=extensao, dir=diretorio)
    caminho = Path(nome)
    try:
        with os.fdopen(descritor, "wb") as destino:
            for bloco in upload.chunks():
                destino.write(bloco)
    except Exception:
        caminho.unlink(missing_ok=True)
        raise
    return caminho


def apagar_temporario(caminho):
    if caminho:
        Path(caminho).unlink(missing_ok=True)


def limpar_temporarios_expirados():
    """Limpeza oportunística de arquivos desta tela; sem percorrer outros temporários."""
    limite_normal = time.time() - TEMPO_TOKEN_MINUTOS * 60
    limite_execucao = time.time() - 24 * 60 * 60
    try:
        for caminho in Path(tempfile.gettempdir()).glob("ppc-importacao-*"):
            try:
                limite = limite_execucao if caminho.name.endswith(".running") else limite_normal
                if caminho.stat().st_mtime < limite:
                    caminho.unlink(missing_ok=True)
            except OSError:
                logger.info("Não foi possível limpar temporário expirado %s", caminho)
    except OSError:
        logger.exception("Não foi possível procurar temporários expirados da importação")


def emitir_evento_importacao(*, comando, modo, nome_arquivo, sha256, usuario, duracao, resumo, sucesso):
    registrar_evento(
        "importacao",
        usuario=usuario,
        comando=comando,
        modo=modo,
        arquivo=Path(nome_arquivo).name[:255],
        sha256=sha256,
        duracao_segundos=round(duracao, 3),
        resumo=str(resumo or "")[:2000],
        sucesso=bool(sucesso),
    )


def execucao_anterior(comando, sha256):
    try:
        evento = (
            EventoUso.objects.filter(
                tipo=EventoUso.Tipo.IMPORTACAO,
                metadados__comando=comando,
                metadados__sha256=sha256,
                metadados__modo="confirmado",
                metadados__sucesso=True,
            )
            .select_related("usuario")
            .order_by("-criado_em")
            .first()
        )
    except Exception:
        logger.exception("Não foi possível consultar importações anteriores")
        return None
    if not evento:
        return None
    usuario = evento.usuario.get_username() if evento.usuario_id else "usuário removido"
    data = timezone.localtime(evento.criado_em).strftime("%d/%m %H:%M")
    return f"Este arquivo já foi importado em {data} por {usuario}."


class _SaidaLimitada(io.StringIO):
    def __init__(self, limite=LIMITE_SAIDA):
        super().__init__()
        self.limite = limite
        self.total = 0

    def write(self, texto):
        self.total += len(texto)
        restante = max(0, self.limite - len(self.getvalue()))
        if restante:
            super().write(texto[:restante])
        return len(texto)

    def getvalue(self):
        valor = super().getvalue()
        if self.total > self.limite:
            return valor[: max(0, self.limite - 30)] + "\n[saída truncada]"
        return valor


def executar_importacao(registro, arquivo_temporario, modo):
    """Executa um comando de forma síncrona e devolve resultado sempre estruturado."""
    inicio = time.monotonic()
    stdout, stderr = _SaidaLimitada(), _SaidaLimitada()
    erro = ""
    try:
        argumentos = dict(registro.get("argumentos", {}))
        if registro["dry_run"]:
            argumentos["confirmar"] = modo == "confirmado"
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            call_command(
                registro["comando"], str(arquivo_temporario),
                stdout=stdout, stderr=stderr, **argumentos,
            )
    except Exception as exc:
        erro = str(exc) or exc.__class__.__name__
        logger.exception("Falha ao executar importação web %s", registro["comando"])
    duracao = time.monotonic() - inicio
    saida = "\n".join(parte for parte in (stdout.getvalue(), stderr.getvalue()) if parte)
    return {
        "sucesso": not bool(erro),
        "saida": saida[:LIMITE_SAIDA],
        "erro": erro[:2000],
        "duracao": round(duracao, 3),
    }
