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
from django.contrib.auth.views import LoginView, LogoutView

# importações do views.py

from ppc.views import (home, ajuda, lista_cursos, gestao_usuarios, criar_usuario, alternar_acesso_usuario, detalhe_curso, criar_ppc, editar_objetivos,
                        editar_permissoes, criar_curso, editar_exposicao_motivos, editar_apresentacao, editar_informacoes_gerais, 
                        editar_principios, editar_expectativas, editar_apendices, editar_atividades_complementares, editar_avaliacao_ensino,
                        editar_avaliacao_projeto_curso, editar_dinamicas_ead, editar_estagio, editar_politicas_integrada, editar_qualificacao, editar_requisitos_legais,
                        editar_tcc, lista_componentes, criar_componente, editar_componente,
                        excluir_bibliografia, editar_bibliografia, editar_relacao, excluir_relacao, editar_referencias, excluir_apendice,
                        gerar_pdf_ppc, lista_nde, criar_membro_nde, editar_membro_nde, excluir_membro_nde,
                        escolher_importacao_ppc, importar_ppc_modelo_novo, importar_ppc_modelo_antigo, remover_componente_da_matriz, detalhe_componente_na_matriz, historico_componente, 
                        editar_vinculo_componente, buscar_componente_existente, adicionar_componente_existente, buscar_cine_brasil_curso, fila_aprovacao_componentes, 
                        rejeitar_componente, aprovar_componente, meus_componentes_pendentes, lista_matrizes_referencia, matriz_referencia_detalhe, mover_item_matriz_referencia, vincular_curso_matriz_referencia,
                           lista_pendencias_por_matriz, revisar_pendencias_matriz, selecionar_matriz_referencia_para_ppc, preview_aplicar_matriz_referencia)

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
    path('ppc/<int:ppc_id>/expectativas/', editar_expectativas, name='editar_expectativas'),
    path('ppc/<int:ppc_id>/tcc/', editar_tcc, name='editar_tcc'),
    path('ppc/<int:ppc_id>/estagio/', editar_estagio, name='editar_estagio'),
    path('ppc/<int:ppc_id>/atividades-complementares/', editar_atividades_complementares, name='editar_atividades_complementares'),
    path('ppc/<int:ppc_id>/politicas-integrada/', editar_politicas_integrada, name='editar_politicas_integrada'),
    path('ppc/<int:ppc_id>/avaliacao-ensino/', editar_avaliacao_ensino, name='editar_avaliacao_ensino'),
    path('ppc/<int:ppc_id>/avaliacao-projeto-curso/', editar_avaliacao_projeto_curso, name='editar_avaliacao_projeto_curso'),
    path('ppc/<int:ppc_id>/qualificacao/', editar_qualificacao, name='editar_qualificacao'),
    path('ppc/<int:ppc_id>/requisitos-legais/', editar_requisitos_legais, name='editar_requisitos_legais'),
    #path('ppc/<int:ppc_id>/bibliografias/', editar_bibliografias, name='editar_bibliografias'),
    path('ppc/<int:ppc_id>/dinamicas-ead/', editar_dinamicas_ead, name='editar_dinamicas_ead'),
    #path('ppc/<int:ppc_id>/estrutura-curricular/', editar_estrutura_curricular, name='editar_estrutura_curricular'),
    path('ppc/<int:ppc_id>/apendices/', editar_apendices, name='editar_apendices'),
    path('ppc/<int:ppc_id>/componentes/', lista_componentes, name='lista_componentes'),
    path('ppc/<int:ppc_id>/componentes/novo/', criar_componente, name='criar_componente'),
    path('componentes-na-matriz/<int:componente_na_matriz_id>/', detalhe_componente_na_matriz, name='detalhe_componente_na_matriz'),
    path('componentes/<int:componente_id>/editar/', editar_componente, name='editar_componente'),
    path('componentes-na-matriz/<int:componente_na_matriz_id>/remover/', remover_componente_da_matriz, name='remover_componente_da_matriz'),
    path('bibliografia/<int:bibliografia_id>/editar/', editar_bibliografia, name='editar_bibliografia'),
    path('bibliografia/<int:bibliografia_id>/excluir/', excluir_bibliografia, name='excluir_bibliografia'),
    path('relacoes/<int:relacao_id>/editar/', editar_relacao, name='editar_relacao'),
    path('relacoes/<int:relacao_id>/excluir/', excluir_relacao, name='excluir_relacao'),
    path('ppc/<int:ppc_id>/referencias/', editar_referencias, name='editar_referencias'),
    path('ppc/<int:ppc_id>/pdf/', gerar_pdf_ppc, name='gerar_pdf_ppc'),
    path('apendice/<int:apendice_id>/excluir/', excluir_apendice, name='excluir_apendice'),
    path('login/', LoginView.as_view(template_name='ppc/login.html'), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('cursos/<int:curso_id>/nde/', lista_nde, name='lista_nde'),
    path('cursos/<int:curso_id>/nde/novo/', criar_membro_nde, name='criar_membro_nde'),
    path('nde/<int:membro_id>/editar/', editar_membro_nde, name='editar_membro_nde'),
    path('nde/<int:membro_id>/excluir/', excluir_membro_nde, name='excluir_membro_nde'),
    path('cursos/<int:curso_id>/importar/', escolher_importacao_ppc, name='importar_ppc_pdf'),
    path('cursos/<int:curso_id>/importar/modelo-novo/', importar_ppc_modelo_novo, name='importar_ppc_modelo_novo'),
    path('cursos/<int:curso_id>/importar/modelo-antigo/', importar_ppc_modelo_antigo, name='importar_ppc_modelo_antigo'),
    path('componentes-na-matriz/<int:componente_na_matriz_id>/vinculo/editar/', editar_vinculo_componente, name='editar_vinculo_componente'),
    path('componentes/<int:componente_id>/historico/', historico_componente, name='historico_componente'),
    path('ppc/<int:ppc_id>/componentes/buscar/', buscar_componente_existente, name='buscar_componente_existente'),
    path('ppc/<int:ppc_id>/componentes/adicionar/<int:componente_id>/', adicionar_componente_existente, name='adicionar_componente_existente'),
    path('cine-brasil-curso/buscar/', buscar_cine_brasil_curso, name='buscar_cine_brasil_curso'),
    path('componentes/aprovacao/', fila_aprovacao_componentes, name='fila_aprovacao_componentes'),
    path('componentes/<int:componente_id>/aprovar/', aprovar_componente, name='aprovar_componente'),
    path('componentes/<int:componente_id>/rejeitar/', rejeitar_componente, name='rejeitar_componente'),
    path('componentes/meus-pendentes/', meus_componentes_pendentes, name='meus_componentes_pendentes'),
    path("matrizes-referencia/", lista_matrizes_referencia, name="lista_matrizes_referencia"),
    path("matrizes-referencia/<int:matriz_id>/", matriz_referencia_detalhe, name="matriz_referencia_detalhe"),
    path("matrizes-referencia/<int:matriz_id>/vincular-curso/", vincular_curso_matriz_referencia, name="vincular_curso_matriz_referencia"),
    path("matrizes-referencia/item/<int:item_id>/mover/", mover_item_matriz_referencia, name="mover_item_matriz_referencia"),
    path("pendencias-matriz/", lista_pendencias_por_matriz, name="lista_pendencias_por_matriz"),
    path("pendencias-matriz/<str:identificador_origem>/", revisar_pendencias_matriz, name="revisar_pendencias_matriz"),
    path("ppc/<int:ppc_id>/aplicar-matriz-referencia/", selecionar_matriz_referencia_para_ppc, name="selecionar_matriz_referencia_para_ppc"),
    path("ppc/<int:ppc_id>/aplicar-matriz-referencia/<int:matriz_id>/", preview_aplicar_matriz_referencia, name="preview_aplicar_matriz_referencia"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
