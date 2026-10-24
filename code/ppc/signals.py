import logging

from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.db import transaction
from django.dispatch import receiver
from simple_history.signals import post_create_historical_record

from .services.auditoria import montar_evento, registro_edicao
from .services.eventos import edicao_suspensa, registrar_evento

logger = logging.getLogger(__name__)


@receiver(user_logged_in)
def registrar_login(sender, request, user, **kwargs):
    registrar_evento("login", usuario=user)


@receiver(user_logged_out)
def registrar_logout(sender, request, user, **kwargs):
    registrar_evento("logout", usuario=user)


@receiver(user_login_failed)
def registrar_falha_login(sender, credentials, request=None, **kwargs):
    registrar_evento("login_falhou", identificador=str(credentials.get("username", ""))[:150])


@receiver(post_create_historical_record)
def registrar_edicao(sender, instance, history_instance, **kwargs):
    if edicao_suspensa() or sender not in registro_edicao():
        return
    try:
        anterior = history_instance.prev_record if history_instance.history_type == "~" else None
        evento = montar_evento(sender, history_instance, anterior)
        if evento:
            with transaction.atomic():
                evento.save()
    except Exception:
        logger.exception("Falha ao registrar evento de edição")