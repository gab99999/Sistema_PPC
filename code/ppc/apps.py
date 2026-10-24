from django.apps import AppConfig


class PpcConfig(AppConfig):
    name = "ppc"

    def ready(self):
        from . import signals  # noqa: F401


