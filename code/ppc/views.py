from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from .models import Curso, PPC
from .forms import (PPCInformacoesGeraisForm, ObjetivosForm, EditarPermissoesForm, CursoForm,
                    InformacoesGeraisForm, ApresentacaoForm, ExposicaoMotivosForm, )

@login_required
def editar_informacoes_gerais(request, ppc_id):
    ppc = get_object_or_404(PPC, id=ppc_id)
    if request.method == 'POST':
        form = InformacoesGeraisForm(request.POST, instance=ppc)
        if form.is_valid():
            form.save()
            return redirect('editar_informacoes_gerais', ppc_id=ppc.id)
    else:
        form = InformacoesGeraisForm(instance=ppc)
    return render(request, 'ppc/editar_informacoes_gerais.html', {'form': form, 'ppc': ppc})


@login_required
def editar_apresentacao(request, ppc_id):
    ppc = get_object_or_404(PPC, id=ppc_id)
    if request.method == 'POST':
        form = ApresentacaoForm(request.POST, instance=ppc)
        if form.is_valid():
            form.save()
            return redirect('editar_apresentacao', ppc_id=ppc.id)
    else:
        form = ApresentacaoForm(instance=ppc)
    return render(request, 'ppc/editar_apresentacao.html', {'form': form, 'ppc': ppc})


@login_required
def editar_exposicao_motivos(request, ppc_id):
    ppc = get_object_or_404(PPC, id=ppc_id)
    if request.method == 'POST':
        form = ExposicaoMotivosForm(request.POST, instance=ppc)
        if form.is_valid():
            form.save()
            return redirect('editar_exposicao_motivos', ppc_id=ppc.id)
    else:
        form = ExposicaoMotivosForm(instance=ppc)
    return render(request, 'ppc/editar_exposicao_motivos.html', {'form': form, 'ppc': ppc})

@login_required
def criar_curso(request):
    if request.method == 'POST':
        form = CursoForm(request.POST)
        if form.is_valid():
            curso = form.save()
            return redirect('detalhe_curso', curso_id=curso.id)
    else:
        form = CursoForm()
    return render(request, 'ppc/criar_curso.html', {'form': form})

@staff_member_required
def editar_permissoes(request, user_id):
    usuario = get_object_or_404(User, id=user_id)
    if request.method == 'POST':
        form = EditarPermissoesForm(request.POST, instance=usuario)
        if form.is_valid():
            form.save()
            return redirect('gestao_usuarios')
    else:
        form = EditarPermissoesForm(instance=usuario)
    return render(request, 'ppc/editar_permissoes.html', {'form': form, 'usuario': usuario})


def home(request):
    return render(request, "ppc/home.html")

def ajuda(request):
    return render(request, 'ppc/ajuda.html')

def lista_cursos(request):
    cursos = Curso.objects.all()
    return render(request, 'ppc/lista_cursos.html', {'cursos': cursos})

@staff_member_required
def gestao_usuarios(request):
    usuarios = User.objects.all().order_by('username')
    return render(request, 'ppc/gestao_usuarios.html', {'usuarios': usuarios})

@staff_member_required
def criar_usuario(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('gestao_usuarios')
    else:
        form = UserCreationForm()
    return render(request, 'ppc/criar_usuario.html', {'form': form})

@staff_member_required
def alternar_acesso_usuario(request, user_id):
    usuario = get_object_or_404(User, id=user_id)
    if request.method == 'POST' and usuario != request.user:
        usuario.is_active = not usuario.is_active
        usuario.save()
    return redirect('gestao_usuarios')

@login_required
def detalhe_curso(request, curso_id):
    curso = get_object_or_404(Curso, id=curso_id)
    ppcs = curso.ppcs.all()
    return render(request, 'ppc/detalhe_curso.html', {'curso': curso, 'ppcs': ppcs})


@login_required
def criar_ppc(request, curso_id):
    curso = get_object_or_404(Curso, id=curso_id)
    if request.method == 'POST':
        form = PPCInformacoesGeraisForm(request.POST)
        if form.is_valid():
            ppc = form.save(commit=False)  # não salva ainda
            ppc.curso = curso              # completa o campo que faltava
            ppc.save()                     # agora sim salva
            return redirect('editar_apresentacao', ppc_id=ppc.id)
    else:
        form = PPCInformacoesGeraisForm()
    return render(request, 'ppc/criar_ppc.html', {'form': form, 'curso': curso})


@login_required
def editar_objetivos(request, ppc_id):
    ppc = get_object_or_404(PPC, id=ppc_id)
    if request.method == 'POST':
        form = ObjetivosForm(request.POST, instance=ppc)
        if form.is_valid():
            form.save()
            return redirect('editar_objetivos', ppc_id=ppc.id)
    else:
        form = ObjetivosForm(instance=ppc)
    return render(request, 'ppc/editar_objetivos.html', {'form': form, 'ppc': ppc})
