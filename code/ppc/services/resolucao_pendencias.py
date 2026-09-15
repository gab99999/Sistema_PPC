# ppc/services/resolucao_pendencias.py
from django.db import transaction
from django.utils import timezone
from ppc.models import (
    ComponenteCurricular,
    MatrizReferenciaCurricular,
    ComponenteNaMatrizReferencia,
)


def resolver_pendencia_ambigua(pendencia, natureza):
    """Recria, a partir do dado bruto guardado na pendência, o vínculo
    ComponenteNaMatrizReferencia que não pôde ser criado no import original
    por falta de natureza definida. Retorna True se resolveu, False se não
    deu pra resolver (ex: núcleo também indefinido — precisa de revisão manual
    direta no dado, não só escolher natureza)."""
    linha = pendencia.dados_brutos

    if not linha.get("nucleo"):
        return False

    matriz, _ = MatrizReferenciaCurricular.objects.get_or_create(
        identificador_origem=linha["identificador_origem"],
    )

    componente, _ = ComponenteCurricular.objects.get_or_create(
        codigo=linha["codigo"],
        defaults={
            "nome": linha["nome"],
            "tipo": "disciplina",
            "nucleo": linha["nucleo"],
            "carga_horaria_teorica": linha["carga_horaria_teorica"],
            "carga_horaria_pratica": linha["carga_horaria_pratica"],
            "unidade_academica_componente": "",
            "ementa": "",
            "status": "aprovado",
        },
    )

    ComponenteNaMatrizReferencia.objects.update_or_create(
        matriz=matriz,
        componente=componente,
        defaults={"periodo": linha["periodo"], "natureza": natureza},
    )

    pendencia.resolvido = True
    pendencia.resolvido_em = timezone.now()
    pendencia.save(update_fields=["resolvido", "resolvido_em"])
    return True