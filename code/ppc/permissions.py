from django.core.exceptions import PermissionDenied
from .models import Curso


def cursos_do_usuario(user):
    if user.is_staff:
        return Curso.objects.all()
    return Curso.objects.filter(vinculos_usuarios__usuario=user)


def exigir_acesso_ao_curso(user, curso):
    if user.is_staff:
        return
    if not curso.vinculos_usuarios.filter(usuario=user).exists():
        raise PermissionDenied

def exigir_acesso_ao_ppc(user, ppc):
    exigir_acesso_ao_curso(user, ppc.curso)


def exigir_acesso_ao_vinculo(user, componente_na_matriz):
    exigir_acesso_ao_curso(user, componente_na_matriz.ppc.curso)