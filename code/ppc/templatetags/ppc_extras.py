from django import template

from ppc.completude import calcular_completude_ppc
from ppc.models import PPC

register = template.Library()


@register.inclusion_tag("ppc/includes/completude_ppc.html")
def painel_completude_ppc(ppc):
    secoes = calcular_completude_ppc(ppc)
    revisadas = sum(s["revisada"] for s in secoes)
    total = len(secoes)
    return {
        "ppc": ppc,
        "pendentes": [s for s in secoes if not s["revisada"]],
        "com_branco": [s for s in secoes if s["campos_em_branco"]],
        "revisadas": revisadas,
        "total": total,
        "percentual": round((revisadas / total) * 100) if total else 0,
    }


@register.inclusion_tag("ppc/includes/barra_revisao.html", takes_context=True)
def barra_revisao_secao(context):
    request = context.get("request")
    match = getattr(request, "resolver_match", None)
    ppc_id = match.kwargs.get("ppc_id") if match else None
    ppc = PPC.objects.filter(id=ppc_id).first() if ppc_id else None
    if ppc is None:
        return {"secoes": []}
    # secoes desta tela: normalmente uma; em editar_apresentacao são duas no EAD
    secoes = [s for s in calcular_completude_ppc(ppc) if s["url"] == match.url_name]
    return {
        "ppc": ppc,
        "secoes": secoes,
        "pendentes": [s for s in secoes if not s["revisada"]],
        "campos_em_branco": sum(s["campos_em_branco"] for s in secoes),
        "total_campos": sum(s["total_campos"] for s in secoes),
        "next": request.get_full_path(),
        "csrf_token": context.get("csrf_token"),
    }