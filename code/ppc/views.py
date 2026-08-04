from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from .models import Curso, PPC, DinamicaEAD, ComponenteCurricular, Bibliografia, Apendice, RelacaoComponente
from .forms import (PPCInformacoesGeraisForm, ObjetivosForm, EditarPermissoesForm, CursoForm,
                    InformacoesGeraisForm, ApresentacaoForm, ExposicaoMotivosForm, PrincipiosForm,
                    ExpectativasForm, TccForm, EstagioForm, AtividadesComplementaresForm,
                     PoliticasIntegradaForm, AvaliacaoEnsinoForm, AvalicaoProjetoCursoForm,
                    QualificacaoForm, RequisitosLegaisForm, ApendiceForm, DinamicaEADForm, 
                    EstruturaCurricularForm, ComponenteCurricularForm, BibliografiaForm, RelacaoComponenteForm,)


@login_required
def editar_relacao(request, relacao_id):
    relacao = get_object_or_404(RelacaoComponente, id=relacao_id)
    componente = relacao.componente
    if request.method == 'POST':
        form = RelacaoComponenteForm(request.POST, instance=relacao, ppc=componente.ppc, componente_atual=componente)
        if form.is_valid():
            form.save()
            return redirect('detalhe_componente', componente_id=componente.id)
    else:
        form = RelacaoComponenteForm(instance=relacao, ppc=componente.ppc, componente_atual=componente)
    return render(request, 'ppc/editar_relacao.html', {
        'form': form, 'componente': componente, 'ppc': componente.ppc
    })


@login_required
def excluir_relacao(request, relacao_id):
    relacao = get_object_or_404(RelacaoComponente, id=relacao_id)
    componente_id = relacao.componente.id
    if request.method == 'POST':
        relacao.delete()
    return redirect('detalhe_componente', componente_id=componente_id)


@login_required
def editar_bibliografia(request, bibliografia_id):
    bib = get_object_or_404(Bibliografia, id=bibliografia_id)
    componente = bib.componente
    if request.method == 'POST':
        form = BibliografiaForm(request.POST, instance=bib)
        if form.is_valid():
            form.save()
            return redirect('detalhe_componente', componente_id=componente.id)
    else:
        form = BibliografiaForm(instance=bib)
    return render(request, 'ppc/editar_bibliografia.html', {
        'form': form, 'componente': componente, 'ppc': componente.ppc
    })


@login_required
def excluir_bibliografia(request, bibliografia_id):
    bib = get_object_or_404(Bibliografia, id=bibliografia_id)
    componente_id = bib.componente.id
    if request.method == 'POST':
        bib.delete()
    return redirect('detalhe_componente', componente_id=componente_id)


@login_required
def lista_componentes(request, ppc_id):
    ppc = get_object_or_404(PPC, id=ppc_id)
    componentes = ppc.componentes_curriculares.all().order_by('periodo', 'nome')
    return render(request, 'ppc/lista_componentes.html', {'ppc': ppc, 'componentes': componentes})


@login_required
def criar_componente(request, ppc_id):
    ppc = get_object_or_404(PPC, id=ppc_id)
    if request.method == 'POST':
        form = ComponenteCurricularForm(request.POST)
        if form.is_valid():
            componente = form.save(commit=False)
            componente.ppc = ppc
            componente.save()
            return redirect('detalhe_componente', componente_id=componente.id)
    else:
        form = ComponenteCurricularForm()
    return render(request, 'ppc/criar_componente.html', {'form': form, 'ppc': ppc})


@login_required
def editar_componente(request, componente_id):
    componente = get_object_or_404(ComponenteCurricular, id=componente_id)
    if request.method == 'POST':
        form = ComponenteCurricularForm(request.POST, instance=componente)
        if form.is_valid():
            form.save()
            return redirect('detalhe_componente', componente_id=componente.id)
    else:
        form = ComponenteCurricularForm(instance=componente)
    return render(request, 'ppc/editar_componente.html', {'form': form, 'componente': componente, 'ppc': componente.ppc})


@login_required
def excluir_componente(request, componente_id):
    componente = get_object_or_404(ComponenteCurricular, id=componente_id)
    ppc_id = componente.ppc.id
    if request.method == 'POST':
        componente.delete()
        return redirect('lista_componentes', ppc_id=ppc_id)
    return render(request, 'ppc/excluir_componente.html', {'componente': componente})


@login_required
def detalhe_componente(request, componente_id):
    componente = get_object_or_404(ComponenteCurricular, id=componente_id)
    bibliografia_form = BibliografiaForm()
    relacao_form = RelacaoComponenteForm(ppc=componente.ppc, componente_atual=componente)

    if request.method == 'POST':
        if 'adicionar_bibliografia' in request.POST:
            bibliografia_form = BibliografiaForm(request.POST)
            if bibliografia_form.is_valid():
                bib = bibliografia_form.save(commit=False)
                bib.componente = componente
                bib.save()
                return redirect('detalhe_componente', componente_id=componente.id)
        elif 'adicionar_relacao' in request.POST:
            relacao_form = RelacaoComponenteForm(request.POST, ppc=componente.ppc, componente_atual=componente)
            if relacao_form.is_valid():
                relacao = relacao_form.save(commit=False)
                relacao.componente = componente
                relacao.save()
                return redirect('detalhe_componente', componente_id=componente.id)

    bibliografias_basicas = componente.bibliografias.filter(tipo='basica')
    bibliografias_complementares = componente.bibliografias.filter(tipo='complementar')

    return render(request, 'ppc/detalhe_componente.html', {
        'ppc': componente.ppc,
        'componente': componente,
        'bibliografia_form': bibliografia_form,
        'relacao_form': relacao_form,
        'bibliografias_basicas': bibliografias_basicas,
        'bibliografias_complementares': bibliografias_complementares,
    })

@login_required
def lista_componentes(request, ppc_id):
    ppc = get_object_or_404(PPC, id=ppc_id)
    componentes = ppc.componentes_curriculares.all().order_by('periodo', 'nome')

    if request.method == 'POST' and 'salvar_descricao' in request.POST:
        estrutura_form = EstruturaCurricularForm(request.POST, instance=ppc)
        if estrutura_form.is_valid():
            estrutura_form.save()
            return redirect('lista_componentes', ppc_id=ppc.id)
    else:
        estrutura_form = EstruturaCurricularForm(instance=ppc)

    return render(request, 'ppc/lista_componentes.html', {
        'ppc': ppc,
        'componentes': componentes,
        'estrutura_form': estrutura_form,
    })


@login_required
def editar_apendices(request, ppc_id):
    ppc = get_object_or_404(PPC, id=ppc_id)
    if request.method == 'POST':
        form = ApendiceForm(request.POST, request.FILES)
        if form.is_valid():
            apendice = form.save(commit=False)
            apendice.ppc = ppc
            apendice.save()
            return redirect('editar_apendices', ppc_id=ppc.id)
    else:
        form = ApendiceForm()
    return render(request, 'ppc/apendices.html', {'form': form, 'ppc': ppc})

@login_required
def editar_dinamicas_ead(request, ppc_id):
    ppc = get_object_or_404(PPC, id=ppc_id)
    dinamica, criado = DinamicaEAD.objects.get_or_create(ppc=ppc)
    if request.method == 'POST':
        form = DinamicaEADForm(request.POST, instance=dinamica)
        if form.is_valid():
            form.save()
            return redirect('editar_dinamicas_ead', ppc_id=ppc.id)
    else:
        form = DinamicaEADForm(instance=dinamica)
    return render(request, 'ppc/editar_dinamicas_ead.html', {'form': form, 'ppc': ppc})
@login_required
def editar_requisitos_legais(request, ppc_id):
    ppc = get_object_or_404(PPC, id=ppc_id)
    if request.method == 'POST':
        form = RequisitosLegaisForm(request.POST, instance=ppc)
        if form.is_valid():
            form.save()
            return redirect('editar_requisitos_legais', ppc_id=ppc.id)
    else:
        form = RequisitosLegaisForm(instance=ppc)
    return render(request, 'ppc/editar_requisitos_legais.html', {'form': form, 'ppc': ppc})

@login_required
def editar_qualificacao(request, ppc_id):
    ppc = get_object_or_404(PPC, id=ppc_id)
    if request.method == 'POST':
        form = QualificacaoForm(request.POST, instance=ppc)
        if form.is_valid():
            form.save()
            return redirect('editar_qualificacao', ppc_id=ppc.id)
    else:
        form = PrincipiosForm(instance=ppc)
    return render(request, 'ppc/editar_qualificacao.html', {'form': form, 'ppc': ppc})

@login_required
def editar_avaliacao_projeto_curso(request, ppc_id):
    ppc = get_object_or_404(PPC, id=ppc_id)
    if request.method == 'POST':
        form = AvalicaoProjetoCursoForm(request.POST, instance=ppc)
        if form.is_valid():
            form.save()
            return redirect('editar_avaliacao_projeto_curso', ppc_id=ppc.id)
    else:
        form = AvalicaoProjetoCursoForm(instance=ppc)
    return render(request, 'ppc/editar_avaliacao_projeto_curso.html', {'form': form, 'ppc': ppc})

@login_required
def editar_avaliacao_ensino(request, ppc_id):
    ppc = get_object_or_404(PPC, id=ppc_id)
    if request.method == 'POST':
        form = AvaliacaoEnsinoForm(request.POST, instance=ppc)
        if form.is_valid():
            form.save()
            return redirect('editar_avaliacao_ensino', ppc_id=ppc.id)
    else:
        form = AvaliacaoEnsinoForm(instance=ppc)
    return render(request, 'ppc/editar_avaliacao_ensino.html', {'form': form, 'ppc': ppc})

@login_required
def editar_politicas_integrada(request, ppc_id):
    ppc = get_object_or_404(PPC, id=ppc_id)
    if request.method == 'POST':
        form = PoliticasIntegradaForm(request.POST, instance=ppc)
        if form.is_valid():
            form.save()
            return redirect('editar_politicas_integrada', ppc_id=ppc.id)
    else:
        form = PoliticasIntegradaForm(instance=ppc)
    return render(request, 'ppc/editar_politicas_integrada.html', {'form': form, 'ppc': ppc})

@login_required
def editar_atividades_complementares(request, ppc_id):
    ppc = get_object_or_404(PPC, id=ppc_id)
    if request.method == 'POST':
        form = AtividadesComplementaresForm(request.POST, instance=ppc)
        if form.is_valid():
            form.save()
            return redirect('editar_atividades_complementares', ppc_id=ppc.id)
    else:
        form = AtividadesComplementaresForm(instance=ppc)
    return render(request, 'ppc/editar_atividades_complementares.html', {'form': form, 'ppc': ppc})

@login_required
def editar_estagio(request, ppc_id):
    ppc = get_object_or_404(PPC, id=ppc_id)
    if request.method == 'POST':
        form = EstagioForm(request.POST, instance=ppc)
        if form.is_valid():
            form.save()
            return redirect('editar_estagio', ppc_id=ppc.id)
    else:
        form = EstagioForm(instance=ppc)
    return render(request, 'ppc/editar_estagio.html', {'form': form, 'ppc': ppc})

@login_required
def editar_tcc(request, ppc_id):
    ppc = get_object_or_404(PPC, id=ppc_id)
    if request.method == 'POST':
        form = TccForm(request.POST, instance=ppc)
        if form.is_valid():
            form.save()
            return redirect('editar_tcc', ppc_id=ppc.id)
    else:
        form = TccForm(instance=ppc)
    return render(request, 'ppc/editar_tcc.html', {'form': form, 'ppc': ppc})

@login_required
def editar_expectativas(request, ppc_id):
    ppc = get_object_or_404(PPC, id=ppc_id)
    if request.method == 'POST':
        form = ExpectativasForm(request.POST, instance=ppc)
        if form.is_valid():
            form.save()
            return redirect('editar_expectativas', ppc_id=ppc.id)
    else:
        form = ExpectativasForm(instance=ppc)
    return render(request, 'ppc/editar_expectativas.html', {'form': form, 'ppc': ppc})

@login_required
def editar_principios(request, ppc_id):
    ppc = get_object_or_404(PPC, id=ppc_id)
    if request.method == 'POST':
        form = PrincipiosForm(request.POST, instance=ppc)
        if form.is_valid():
            form.save()
            return redirect('editar_principios', ppc_id=ppc.id)
    else:
        form = PrincipiosForm(instance=ppc)
    return render(request, 'ppc/editar_principios.html', {'form': form, 'ppc': ppc})

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
