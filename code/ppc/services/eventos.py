import logging
from contextlib import contextmanager
from contextvars import ContextVar

from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

logger = logging.getLogger(__name__)

_edicao_suspensa = ContextVar("eventos_edicao_suspensos", default=False)


@contextmanager
def suspender_eventos_edicao():
    """Dentro do bloco, o history continua sendo gravado, mas EventoEdicao não.
    Use em operações em lote (duplicar PPC, aplicar matriz, importar) e registre um evento-resumo."""
    token = _edicao_suspensa.set(True)
    try:
        yield
    finally:
        _edicao_suspensa.reset(token)


def edicao_suspensa():
    return _edicao_suspensa.get()


def registrar_evento(tipo, usuario=None, ppc=None, curso=None, identificador="", **metadados):
    """Registra um EventoUso. Nunca levanta exceção."""
    try:
        from ppc.models import EventoUso

        if usuario is not None and not getattr(usuario, "is_authenticated", False):
            usuario = None
        curso_id = curso.pk if curso is not None else (ppc.curso_id if ppc is not None else None)
        with transaction.atomic():
            EventoUso.objects.create(
                tipo=tipo,
                usuario=usuario,
                ppc=ppc,
                curso_id=curso_id,
                identificador=identificador,
                metadados=metadados,
            )
    except Exception:
        logger.exception("Falha ao registrar evento de uso (%s)", tipo)


def registrar_uso(usuario, url_name):
    """Incrementa o contador de páginas vistas (usuário, dia, hora, tela). Nunca levanta exceção."""
    try:
        from ppc.models import UsoDiario

        agora = timezone.localtime()
        filtro = dict(usuario=usuario, data=agora.date(), hora=agora.hour, url_name=url_name[:100])
        with transaction.atomic():
            if not UsoDiario.objects.filter(**filtro).update(contagem=F("contagem") + 1):
                try:
                    with transaction.atomic():
                        UsoDiario.objects.create(contagem=1, **filtro)
                except IntegrityError:  # corrida: outra requisição criou primeiro
                    UsoDiario.objects.filter(**filtro).update(contagem=F("contagem") + 1)
    except Exception:
        logger.exception("Falha ao registrar uso de tela")