from django.core.exceptions import ValidationError

def validar_multiplo_de_8(value):
    if value is None:
        return
    if value % 8 != 0:
        raise ValidationError(
            f"{value} não é múltiplo de 8. A carga horária deve ser múltipla de 8 "
            f"(ex: 32, 40, 64, 72...).",
            code="nao_multiplo_de_8",
        )