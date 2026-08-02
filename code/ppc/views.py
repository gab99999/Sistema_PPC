from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render, redirect, get_object_or_404
from ppc.models import Curso


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
