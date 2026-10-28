from django.core.exceptions import PermissionDenied

from .models import (
    PPC, ComponenteNaMatriz, MembroNDE, Bibliografia,
    RelacaoComponente, Apendice, VinculoUsuarioCurso,
)
# topo do arquivo
from .services.eventos import registrar_uso

# final do arquivo
class UsoMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        user = getattr(request, "user", None)
        match = request.resolver_match
        if (
            request.method == "GET"
            and response.status_code == 200
            and user is not None and user.is_authenticated
            and match is not None and match.url_name
            and "admin" not in match.namespaces
            and response.get("Content-Type", "").startswith("text/html")
        ):
            registrar_uso(user, match.url_name)
        return response


def _primeiro(model, campo):
    return lambda valor: model.objects.filter(id=valor).values_list(campo, flat=True).first()


# nome do parâmetro na URL -> função que devolve o id do curso dono daquele objeto
RESOLVEDORES = {
    'curso_id': lambda valor: valor,
    'ppc_id': _primeiro(PPC, 'curso_id'),
    'componente_na_matriz_id': _primeiro(ComponenteNaMatriz, 'ppc__curso_id'),
    'membro_id': _primeiro(MembroNDE, 'curso_id'),
    'bibliografia_id': _primeiro(Bibliografia, 'componente_na_matriz__ppc__curso_id'),
    'relacao_id': _primeiro(RelacaoComponente, 'componente_na_matriz__ppc__curso_id'),
    'apendice_id': _primeiro(Apendice, 'ppc__curso_id'),
}


class AcessoPorCursoMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        user = request.user
        # anônimo: o login_required da view cuida; staff (DAA): acesso total
        if not user.is_authenticated or user.is_staff:
            return None

        # As telas de equivalência, como a tela das matrizes de referência,
        # são abertas a qualquer usuário autenticado.
        if request.resolver_match and request.resolver_match.url_name in {
            "equivalencias_ppc", "candidatos_equivalencia_ppc",
        }:
            return None

        for nome, resolver in RESOLVEDORES.items():
            if nome in view_kwargs:
                curso_id = resolver(view_kwargs[nome])
                if curso_id is None:
                    return None  # objeto não existe: a view responde 404 normalmente
                tem_vinculo = VinculoUsuarioCurso.objects.filter(
                    usuario=user, curso_id=curso_id
                ).exists()
                if not tem_vinculo:
                    raise PermissionDenied
        return None
