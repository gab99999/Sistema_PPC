from django import template

from ppc.completude import calcular_completude_ppc


register = template.Library()


@register.inclusion_tag("ppc/includes/completude_ppc.html")
def painel_completude_ppc(ppc):
    secoes = calcular_completude_ppc(ppc)
    preenchidas = sum(secao["preenchida"] for secao in secoes)
    total = len(secoes)
    return {
        "ppc": ppc,
        "secoes": secoes,
        "preenchidas": preenchidas,
        "total": total,
        "percentual": round((preenchidas / total) * 100) if total else 0,
    }
