"""Validação compartilhada dos códigos do catálogo de componentes."""
from django.core.exceptions import ValidationError


def normalizar_codigo_componente(codigo):
    return (codigo or "").strip().casefold()


def validar_codigo_componente(codigo, instancia=None):
    normalizado = normalizar_codigo_componente(codigo)
    if not normalizado:
        return
    from ppc.models import ComponenteCurricular

    if instancia is not None and instancia.pk:
        anterior = ComponenteCurricular.objects.filter(pk=instancia.pk).values_list("codigo", flat=True).first()
        if anterior is not None and normalizar_codigo_componente(anterior) == normalizado:
            return  # legado duplicado inalterado não pode bloquear edição

    queryset = ComponenteCurricular.objects.all()
    if instancia is not None and instancia.pk:
        queryset = queryset.exclude(pk=instancia.pk)
    for outro_codigo in queryset.values_list("codigo", flat=True).iterator(chunk_size=500):
        if normalizar_codigo_componente(outro_codigo) == normalizado:
            raise ValidationError("Já existe um componente com esse código (ignorando maiúsculas e espaços nas pontas).")
