"""Busca limitada e sem extensões de banco para nomes parecidos no catálogo."""
import unicodedata
from difflib import SequenceMatcher

from django.db.models import Q
from django.urls import reverse

from ppc.models import ComponenteCurricular
from ppc.services.codigos_componentes import normalizar_codigo_componente
from ppc.services.regras_equivalencia import carga_total_segura

LIMITE_CANDIDATOS = 300
LIMITE_RESULTADOS = 5
LIMIAR_SIMILARIDADE = 0.42


def normalizar_nome_componente(valor):
    sem_acentos = "".join(
        caractere for caractere in unicodedata.normalize("NFKD", str(valor or ""))
        if not unicodedata.combining(caractere)
    )
    return " ".join(sem_acentos.casefold().split())


def _pontuar(consulta, nome):
    nome_normalizado = normalizar_nome_componente(nome)
    razao = SequenceMatcher(None, consulta, nome_normalizado).ratio()
    palavras = set(consulta.split())
    palavras_nome = set(nome_normalizado.split())
    intersecao = len(palavras & palavras_nome) / max(1, len(palavras))
    if consulta and consulta in nome_normalizado:
        razao = max(razao, 0.8)
    return max(razao, intersecao * 0.8)


def sugerir_componentes(matriz, *, nome="", codigo=""):
    nome = (nome or "").strip()
    codigo = (codigo or "").strip()
    consulta = normalizar_nome_componente(nome)
    codigo_normalizado = normalizar_codigo_componente(codigo)

    codigo_igual = False
    ids_codigo_igual = []
    if codigo_normalizado:
        ids_codigo_igual = [pk for pk, valor in ComponenteCurricular.objects.values_list("pk", "codigo").iterator(chunk_size=500)
                            if normalizar_codigo_componente(valor) == codigo_normalizado]
        codigo_igual = bool(ids_codigo_igual)

    if len(consulta) < 3:
        candidatos = []
    else:
        filtro = Q()
        for palavra in consulta.split():
            # A busca literal aceita consultas parciais; o prefixo curto cobre diferenças de acento
            # em SQLite sem depender de collation ou função de banco específica.
            prefixo = palavra[:3]
            filtro |= Q(nome__icontains=palavra) | Q(nome__istartswith=prefixo)
        candidatos = list(ComponenteCurricular.objects.filter(filtro).order_by("nome", "pk")[:LIMITE_CANDIDATOS])
    if ids_codigo_igual:
        vistos = {item.pk for item in candidatos}
        candidatos.extend(
            item for item in ComponenteCurricular.objects.filter(pk__in=ids_codigo_igual).order_by("pk")
            if item.pk not in vistos
        )

    pontuados = []
    for componente in candidatos:
        score = _pontuar(consulta, componente.nome)
        codigo_componente_igual = bool(
            codigo_normalizado and normalizar_codigo_componente(componente.codigo) == codigo_normalizado
        )
        if score >= LIMIAR_SIMILARIDADE or codigo_componente_igual:
            carga, motivo = carga_total_segura(componente)
            pontuados.append({
                "id": componente.pk,
                "codigo": componente.codigo or "",
                "nome": componente.nome,
                "status": componente.status,
                "status_display": componente.get_status_display(),
                "carga_horaria": carga,
                "carga_horaria_label": f"{carga} h" if carga is not None else "Carga horária incompleta",
                "url_detalhe": reverse("detalhe_componente_existente_matriz_referencia", args=(matriz.pk, componente.pk)),
                "codigo_igual": codigo_componente_igual,
                "score": round(score, 3),
                "motivo_carga": motivo,
            })
    pontuados.sort(key=lambda item: (not item["codigo_igual"], -item["score"], item["nome"].casefold(), item["id"]))
    return {
        "itens": pontuados[:LIMITE_RESULTADOS],
        "codigo_igual": codigo_igual,
        "nome_minimo": len(consulta) < 3,
        "candidatos_avaliados": len(candidatos),
    }
