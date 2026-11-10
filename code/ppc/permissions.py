from django.core.exceptions import PermissionDenied
from .models import Curso
from .models import MatrizReferenciaCurricular, VinculoUsuarioCurso


def _tem_vinculo(user, curso_id):
    return (
        curso_id is not None
        and VinculoUsuarioCurso.objects.filter(usuario=user, curso_id=curso_id).exists()
    )


def pode_editar_matriz(user, matriz):
    if user.is_staff:
        return True
    return (
        matriz.status == MatrizReferenciaCurricular.STATUS_EM_MUDANCA
        and _tem_vinculo(user, matriz.curso_id)
    )


def pode_criar_edicao(user, matriz_origem):
    if user.is_staff:
        return True
    return _tem_vinculo(user, matriz_origem.curso_id)


def exigir_edicao_matriz(user, matriz):
    if not pode_editar_matriz(user, matriz):
        raise PermissionDenied


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