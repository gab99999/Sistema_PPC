"""Configuração isolada para testes sem conexão ao MySQL de desenvolvimento."""

import importlib.util
import sys
import types

from .settings import *  # noqa: F401,F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# As views importam o leitor de PDF no carregamento do URLconf. A suíte
# ppc.tests não exercita essa integração; evita falha de import quando a
# dependência opcional não está instalada no ambiente de testes.
if importlib.util.find_spec("pdfplumber") is None:
    sys.modules["pdfplumber"] = types.ModuleType("pdfplumber")
