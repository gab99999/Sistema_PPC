"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

# importações do views.py

from ppc.views import (home, ajuda, lista_cursos, gestao_usuarios, criar_usuario, alternar_acesso_usuario, detalhe_curso, criar_ppc, editar_objetivos,
                        editar_permissoes, criar_curso, editar_exposicao_motivos, editar_apresentacao, editar_informacoes_gerais, 
                        editar_principios, )

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', home, name='home'),
    path('ajuda/', ajuda, name='ajuda'),
    path('lista_cursos/', lista_cursos, name='lista_cursos'),
    path('gestao_usuarios/', gestao_usuarios, name='gestao_usuarios'),
    path('gestao_usuarios/criar/', criar_usuario, name='criar_usuario'),
    path('gestao_usuarios/<int:user_id>/alternar/', alternar_acesso_usuario, name='alternar_acesso_usuario'),
    path('cursos/<int:curso_id>/', detalhe_curso, name='detalhe_curso'),
    path('cursos/<int:curso_id>/novo_ppc/', criar_ppc, name='criar_ppc'),
    path('ppc/<int:ppc_id>/objetivos/', editar_objetivos, name='editar_objetivos'),
    path("ckeditor5/", include('django_ckeditor_5.urls')),
    path('gestao_usuarios/<int:user_id>/permissoes/', editar_permissoes, name='editar_permissoes'),
    path('cursos/novo/', criar_curso, name='criar_curso'),
    path('ppc/<int:ppc_id>/informacoes-gerais/', editar_informacoes_gerais, name='editar_informacoes_gerais'),
    path('ppc/<int:ppc_id>/apresentacao/', editar_apresentacao, name='editar_apresentacao'),
    path('ppc/<int:ppc_id>/exposicao-motivos/', editar_exposicao_motivos, name='editar_exposicao_motivos'),
    path('ppc/<int:ppc_id>/principios/', editar_principios, name='editar_principios'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)