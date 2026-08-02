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
from django.urls import path

# importações do views.py

from ppc.views import home, ajuda, lista_cursos, gestao_usuarios, criar_usuario, alternar_acesso_usuario

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', home, name='home'),
    path('ajuda/', ajuda, name='ajuda'),
    path('lista_cursos/', lista_cursos, name='lista_cursos'),
    path('gestao_usuarios/', gestao_usuarios, name='gestao_usuarios'),
    path('gestao_usuarios/criar/', criar_usuario, name='criar_usuario'),
    path('gestao_usuarios/<int:user_id>/alternar/', alternar_acesso_usuario, name='alternar_acesso_usuario'),
]