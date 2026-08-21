from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.contrib import messages
from django.template.loader import render_to_string
from django.db.models import Prefetch
from django.utils.text import slugify
from weasyprint import HTML
from ppc.testes.analisar_pdf_uma_chamada import analisar_pdf_adaptativo, ErroOpenRouter
from .models import Curso, PPC, DinamicaEAD, ComponenteCurricular, Bibliografia, Apendice, RelacaoComponente, MembroNDE
from .forms import (PPCInformacoesGeraisForm, ObjetivosForm, EditarPermissoesForm, CursoForm,
                    InformacoesGeraisForm, ApresentacaoForm, ExposicaoMotivosForm, PrincipiosForm,
                    ExpectativasForm, TccForm, EstagioForm, AtividadesComplementaresForm,
                     PoliticasIntegradaForm, AvaliacaoEnsinoForm, AvalicaoProjetoCursoForm,
                    QualificacaoForm, RequisitosLegaisForm, ApendiceForm, DinamicaEADForm, 
                    EstruturaCurricularForm, ComponenteCurricularForm, BibliografiaForm, RelacaoComponenteForm,
                    ReferenciasForm, MembroNDEForm, ImportarPDFForm, ImportarPPCModeloAntigoForm, LimitesCargaHorariaFormSet, )
from django.db.models import Q
from .importacao import extrair_dados_pdf
from .importacao_modelos_antigos import ErroImportacaoPPC, preparar_importacao_modelo_antigo
import logging
from types import SimpleNamespace
from django.db import transaction

import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)



CAMPOS_PPC_VALIDOS = {f.name for f in PPC._meta.get_fields()}

@login_required
def escolher_importacao_ppc(request, curso_id):
    curso = get_object_or_404(Curso, id=curso_id)
    return render(request, 'ppc/importar_ppc.html', {'curso': curso})


@login_required
def importar_ppc_modelo_novo(request, curso_id):
    """Fluxo legado: preserva a extração determinística de ``importacao.py``."""
    curso = get_object_or_404(Curso, id=curso_id)
    if request.method == 'POST':
        form = ImportarPDFForm(request.POST, request.FILES)
        if form.is_valid():
            dados = extrair_dados_pdf(request.FILES['arquivo'])
            dados_ppc = {k: v for k, v in dados.items() if k in CAMPOS_PPC_VALIDOS}
            dados_ppc.setdefault('modalidade', 'presencial')
            dados_ppc.setdefault('grau_academico', 'bacharelado')
            dados_ppc.setdefault('tipo_ppc', 'novo')
            dados_ppc.setdefault('carga_horaria_total', 0)
            dados_ppc.setdefault('numero_vagas_anuais', 0)
            dados_ppc.setdefault('duracao_minima_semestres', 0)
            dados_ppc.setdefault('duracao_media_semestres', 0)
            dados_ppc.setdefault('duracao_maxima_semestres', 0)
            dados_ppc['status'] = 'rascunho'
            ppc = PPC.objects.create(curso=curso, **dados_ppc)
            return redirect('editar_informacoes_gerais', ppc_id=ppc.id)
    else:
        form = ImportarPDFForm()
    return render(request, 'ppc/importar_ppc_modelo_novo.html', {'form': form, 'curso': curso})

def _inteiro_nao_negativo(valor) -> int:
    """PositiveIntegerField não aceita None nem negativo; dado corrompido vira 0
    para revisão humana posterior, igual ao tratamento de campo ausente."""
    try:
        numero = int(valor)
    except (TypeError, ValueError):
        return 0
    return numero if numero >= 0 else 0


@login_required
def importar_ppc_modelo_antigo(request, curso_id):
    """Caminho 2: cria PPC em rascunho com extração por IA, com revisão humana obrigatória depois."""
    curso = get_object_or_404(Curso, id=curso_id)
    if request.method == 'POST':
        form = ImportarPPCModeloAntigoForm(request.POST, request.FILES)
        if not form.is_valid():
            return _resposta_erro_importacao(request, form, curso, "Revise os dados informados.", 400)

        chave = f"importacao_antiga_em_andamento_{curso.id}"
        if request.session.get(chave):
            return _resposta_erro_importacao(request, form, curso, "Já existe uma importação em andamento para este curso.", 409)
        request.session[chave] = True
        request.session.modified = True

        arquivo_temporario = None
        try:
            # analisar_pdf_adaptativo espera um Path em disco, não o UploadedFile do Django.
            upload = form.cleaned_data['arquivo']
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
                for pedaco in upload.chunks():
                    tmp.write(pedaco)
                arquivo_temporario = Path(tmp.name)

            dados, diagnostico = analisar_pdf_adaptativo(arquivo_temporario)
            with transaction.atomic():
                ppc = criar_ppc_rascunho_a_partir_de_dados_ia(dados, curso)
        except (ErroOpenRouter, ValueError) as erro:
            logger.exception("Falha na importação antiga do PPC, curso id=%s", curso.id)
            return _resposta_erro_importacao(request, form, curso, _mensagem_amigavel_importacao(erro), 422)
        except Exception:
            logger.exception("Erro inesperado na importação antiga do PPC, curso id=%s", curso.id)
            return _resposta_erro_importacao(request, form, curso, "Não foi possível concluir a importação agora. Tente novamente em alguns minutos.", 500)
        finally:
            if arquivo_temporario is not None:
                arquivo_temporario.unlink(missing_ok=True)
            request.session.pop(chave, None)
            request.session.modified = True

        destino = redirect('editar_informacoes_gerais', ppc_id=ppc.id).url
        if _requisicao_ajax(request):
            return JsonResponse({"ok": True, "redirect_url": destino})
        messages.success(request, "PPC importado como rascunho. Revise todos os campos antes de finalizar.")
        return redirect(destino)
    return render(request, 'ppc/importar_ppc_modelo_antigo.html', {'form': ImportarPPCModeloAntigoForm(), 'curso': curso})

CAMPOS_PPC_VALIDOS = {  # supondo que já existe algo assim no Caminho 1 — reaproveite se já tiver
    'modalidade', 'grau_academico', 'turno_funcionamento', 'carga_horaria_total',
    'numero_vagas_anuais', 'duracao_minima_semestres', 'duracao_media_semestres',
    'duracao_maxima_semestres', 'diretor', 'vice_diretor', 'coordenador_curso',
    'numero_resolucao', 'tipo_ppc', 'publico_alvo_ead', 'ato_integracao_uab',
    'ato_credenciamento_mec', 'polos_ead', 'apresentacao_texto', 'exposicao_motivos',
    'objetivo_geral', 'objetivo_especifico', 'principios_geral',
    'principios_pratica_profissional', 'principios_formacao_tecnica',
    'principios_formacao_etica_social', 'principios_interdisciplinaridade',
    'principios_articulacao_teoria_pratica', 'perfil_curso', 'perfil_habilidades',
    'estrutura_curricular_descricao', 'estrutura_curricular_informacoes_complementares',
    'estagio', 'tcc', 'atividades_complementares', 'politicas_integrada',
    'avaliacao_ensino_aprendizagem', 'avaliacao_projeto_curso', 'qualificacao',
    'diretrizes_curriculares_nacionais_curso', 'diretrizes_curriculares_nacionais_educacao_basica',
    'diretrizes_etnico_raciais_historia_cultura_afro_indigena', 'diretrizes_educacao_direitos_humanos',
    'protecao_direitos_pessoa_transtorno_espectro_autista', 'componente_curricular_libras',
    'politicas_educacao_ambiental', 'diretrizes_formacao_professores_educacao_basica',
    'condicoes_acesso_pessoas_deficiencia_mobilidade_reduzida', 'bibliografias_ppc',
}

FALLBACKS_PPC_OBRIGATORIOS = {
    'modalidade': 'presencial',
    'grau_academico': 'bacharelado',
    'tipo_ppc': 'novo',
    'carga_horaria_total': 0,
    'numero_vagas_anuais': 0,
    'duracao_minima_semestres': 0,
    'duracao_media_semestres': 0,
    'duracao_maxima_semestres': 0,
}


def criar_ppc_rascunho_a_partir_de_dados_ia(dados: dict, curso) -> "PPC":
    dados_ppc = {k: v for k, v in dados.get('ppc', {}).items() if k in CAMPOS_PPC_VALIDOS and v is not None}
    for campo, valor_padrao in FALLBACKS_PPC_OBRIGATORIOS.items():
        dados_ppc.setdefault(campo, valor_padrao)
    dados_ppc['status'] = 'rascunho'

    ppc = PPC.objects.create(curso=curso, **dados_ppc)

    mapa_componentes = {}
    for item in dados.get('componentes_curriculares', []):
        componente = ComponenteCurricular.objects.create(
            ppc=ppc,
            nome=item.get('nome') or '',
            tipo=item.get('tipo') or '',
            natureza=item.get('natureza') or '',
            nucleo=item.get('nucleo') or '',
            periodo=_inteiro_nao_negativo(item.get('periodo')),
            carga_horaria_teorica=_inteiro_nao_negativo(item.get('carga_horaria_teorica')),
            carga_horaria_pratica=_inteiro_nao_negativo(item.get('carga_horaria_pratica')),
            carga_horaria_pcc=_inteiro_nao_negativo(item.get('carga_horaria_pcc')),
            unidade_academica_componente=item.get('unidade_academica_componente') or '',
            ementa=item.get('ementa') or '',
        )
        mapa_componentes[item.get('nome')] = componente

        for bib in item.get('bibliografias', []):
            Bibliografia.objects.create(
                componente=componente,
                tipo=bib.get('tipo') or '',
                titulo=bib.get('titulo') or '',
                autores=bib.get('autores') or '',
                editora=bib.get('editora') or '',
                cidade=bib.get('cidade') or '',
                ano=bib.get('ano'),
            )

    for item in dados.get('componentes_curriculares', []):
        origem = mapa_componentes.get(item.get('nome'))
        if origem is None:
            continue
        for relacao in item.get('relacoes', []):
            destino = mapa_componentes.get(relacao.get('componente_relacionado_nome'))
            if destino is None or destino == origem:
                continue  # componente relacionado fora do PDF, ou auto-relação — ignora
            RelacaoComponente.objects.get_or_create(
                componente=origem,
                componente_relacionado=destino,
                tipo=relacao.get('tipo') or '',
            )

    return ppc

def _requisicao_ajax(request):
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest'


def _resposta_erro_importacao(request, form, curso, mensagem, status):
    if _requisicao_ajax(request):
        return JsonResponse({"ok": False, "erro": mensagem, "campos": form.errors}, status=status)
    form.add_error(None, mensagem)
    return render(request, 'ppc/importar_ppc_modelo_antigo.html', {'form': form, 'curso': curso}, status=status)


def _rascunho_importacao_antiga(request, ppc_id):
    """Obtém somente o rascunho associado ao PPC desta sessão."""
    rascunho = request.session.get(f"rascunho_importacao_antiga_{ppc_id}", {})
    return rascunho if isinstance(rascunho, dict) else {}


def _initial_rascunho(request, ppc, classe_form, secao="ppc"):
    """Sobrepõe o banco apenas na primeira apresentação do campo em revisão."""
    dados = _rascunho_importacao_antiga(request, ppc.id).get("dados", {})
    origem = dados.get(secao, {}) if isinstance(dados, dict) else {}
    campos = getattr(classe_form.Meta, "fields", [])
    return {campo: origem[campo] for campo in campos if origem.get(campo) is not None}


def _consumir_campos_rascunho(request, ppc, classe_form, secao="ppc"):
    """Após salvar uma seção, o valor manual passa a ter prioridade sobre o rascunho."""
    chave = f"rascunho_importacao_antiga_{ppc.id}"
    rascunho = _rascunho_importacao_antiga(request, ppc.id)
    dados = rascunho.get("dados", {})
    origem = dados.get(secao, {}) if isinstance(dados, dict) else {}
    for campo in getattr(classe_form.Meta, "fields", []):
        origem.pop(campo, None)
    if origem is not None:
        dados[secao] = origem
    request.session[chave] = rascunho
    request.session.modified = True


def _mensagem_amigavel_importacao(erro):
    detalhe = str(erro).lower()
    if 'timeout' in detalhe or '504' in detalhe:
        return "A análise demorou mais do que o esperado. Nenhuma alteração foi aplicada; tente novamente."
    if 'openrouter' in detalhe or 'provider' in detalhe:
        return "O serviço de análise não respondeu corretamente. Tente novamente em alguns minutos."
    if 'json' in detalhe or 'estrutura' in detalhe:
        return "O resultado da análise não pôde ser validado. Tente novamente com o PDF original."
    if 'pdf' in detalhe or 'texto extraível' in detalhe:
        return "Não foi possível ler este PDF. Confirme se o arquivo é o documento original e tente novamente."
    return "A importação falhou. Verifique o arquivo e tente novamente."

@login_required
def lista_nde(request, curso_id):
    curso = get_object_or_404(Curso, id=curso_id)
    membros = curso.membros_nde.filter(ativo=True).order_by('-funcao', 'nome')
    rascunho = _rascunho_importacao_antiga(request, request.GET.get('ppc_id', 0))
    membros_rascunho = rascunho.get('dados', {}).get('membros_nde', [])
    return render(request, 'ppc/lista_nde.html', {'curso': curso, 'membros': membros, 'membros_rascunho': membros_rascunho})


@login_required
def criar_membro_nde(request, curso_id):
    curso = get_object_or_404(Curso, id=curso_id)
    if request.method == 'POST':
        form = MembroNDEForm(request.POST)
        if form.is_valid():
            membro = form.save(commit=False)
            membro.curso = curso
            membro.save()
            return redirect('lista_nde', curso_id=curso.id)
    else:
        form = MembroNDEForm()
    return render(request, 'ppc/criar_membro_nde.html', {'form': form, 'curso': curso})


@login_required
def editar_membro_nde(request, membro_id):
    membro = get_object_or_404(MembroNDE, id=membro_id)
    if request.method == 'POST':
        form = MembroNDEForm(request.POST, instance=membro)
        if form.is_valid():
            form.save()
            return redirect('lista_nde', curso_id=membro.curso.id)
    else:
        form = MembroNDEForm(instance=membro)
    return render(request, 'ppc/editar_membro_nde.html', {'form': form, 'curso': membro.curso})


@login_required
def excluir_membro_nde(request, membro_id):
    membro = get_object_or_404(MembroNDE, id=membro_id)
    curso_id = membro.curso.id
    if request.method == 'POST':
        membro.delete()
    return redirect('lista_nde', curso_id=curso_id)


def lista_cursos(request):
    query = request.GET.get('q', '')
    cursos = Curso.objects.all()
    if query:
        cursos = cursos.filter(
            Q(nome__icontains=query) |
            Q(unidade_academica__icontains=query) |
            Q(area_conhecimento__icontains=query)
        )
    return render(request, 'ppc/lista_cursos.html', {'cursos': cursos, 'query': query})

@login_required
def excluir_apendice(request, apendice_id):
    apendice = get_object_or_404(Apendice, id=apendice_id)
    ppc_id = apendice.ppc.id
    if request.method == 'POST':
        apendice.delete()
    return redirect('editar_apendices', ppc_id=ppc_id)


@login_required
def editar_referencias(request, ppc_id):
    ppc = get_object_or_404(PPC, id=ppc_id)
    if request.method == 'POST':
        form = ReferenciasForm(request.POST, instance=ppc)
        if form.is_valid():
            form.save()
            return redirect('editar_referencias', ppc_id=ppc.id)
    else:
        form = ReferenciasForm(instance=ppc, initial=_initial_rascunho(request, ppc, ReferenciasForm))
    return render(request, 'ppc/editar_referencias.html', {'form': form, 'ppc': ppc})


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
        estrutura_form = EstruturaCurricularForm(instance=ppc, initial=_initial_rascunho(request, ppc, EstruturaCurricularForm))

    dados_rascunho = _rascunho_importacao_antiga(request, ppc.id).get('dados', {})

    return render(request, 'ppc/lista_componentes.html', {
        'ppc': ppc,
        'componentes': componentes,
        'estrutura_form': estrutura_form,
        'componentes_rascunho': dados_rascunho.get('componentes_curriculares', []),
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
    apendices_rascunho = _rascunho_importacao_antiga(request, ppc.id).get('dados', {}).get('apendices', [])
    return render(request, 'ppc/apendices.html', {'form': form, 'ppc': ppc, 'apendices_rascunho': apendices_rascunho})

@login_required
def editar_dinamicas_ead(request, ppc_id):
    ppc = get_object_or_404(PPC, id=ppc_id)
    dinamica = DinamicaEAD.objects.filter(ppc=ppc).first() or DinamicaEAD(ppc=ppc)
    if request.method == 'POST':
        form = DinamicaEADForm(request.POST, instance=dinamica)
        if form.is_valid():
            form.save()
            return redirect('editar_dinamicas_ead', ppc_id=ppc.id)
    else:
        form = DinamicaEADForm(instance=dinamica, initial=_initial_rascunho(request, ppc, DinamicaEADForm, 'dinamica_ead'))
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
        form = RequisitosLegaisForm(instance=ppc, initial=_initial_rascunho(request, ppc, RequisitosLegaisForm))
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
        form = QualificacaoForm(instance=ppc, initial=_initial_rascunho(request, ppc, QualificacaoForm))
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
        form = AvalicaoProjetoCursoForm(instance=ppc, initial=_initial_rascunho(request, ppc, AvalicaoProjetoCursoForm))
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
        form = AvaliacaoEnsinoForm(instance=ppc, initial=_initial_rascunho(request, ppc, AvaliacaoEnsinoForm))
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
        form = PoliticasIntegradaForm(instance=ppc, initial=_initial_rascunho(request, ppc, PoliticasIntegradaForm))
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
        form = AtividadesComplementaresForm(instance=ppc, initial=_initial_rascunho(request, ppc, AtividadesComplementaresForm))
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
        form = EstagioForm(instance=ppc, initial=_initial_rascunho(request, ppc, EstagioForm))
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
        form = TccForm(instance=ppc, initial=_initial_rascunho(request, ppc, TccForm))
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
        form = ExpectativasForm(instance=ppc, initial=_initial_rascunho(request, ppc, ExpectativasForm))
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
        form = PrincipiosForm(instance=ppc, initial=_initial_rascunho(request, ppc, PrincipiosForm))
    return render(request, 'ppc/editar_principios.html', {'form': form, 'ppc': ppc})

@login_required
def editar_informacoes_gerais(request, ppc_id):
    ppc = get_object_or_404(PPC, id=ppc_id)
    if request.method == 'POST':
        form = InformacoesGeraisForm(request.POST, instance=ppc, curso=ppc.curso)
        if form.is_valid():
            form.save()
            _consumir_campos_rascunho(request, ppc, InformacoesGeraisForm)
            return redirect('editar_informacoes_gerais', ppc_id=ppc.id)
    else:
        form = InformacoesGeraisForm(instance=ppc, initial=_initial_rascunho(request, ppc, InformacoesGeraisForm))
    return render(request, 'ppc/editar_informacoes_gerais.html', {'form': form, 'ppc': ppc})


@login_required
def editar_apresentacao(request, ppc_id):
    ppc = get_object_or_404(PPC, id=ppc_id)
    if request.method == 'POST':
        form = ApresentacaoForm(request.POST, instance=ppc)
        if form.is_valid():
            form.save()
            _consumir_campos_rascunho(request, ppc, ApresentacaoForm)
            return redirect('editar_apresentacao', ppc_id=ppc.id)
    else:
        form = ApresentacaoForm(instance=ppc, initial=_initial_rascunho(request, ppc, ApresentacaoForm))
    return render(request, 'ppc/editar_apresentacao.html', {'form': form, 'ppc': ppc})


@login_required
def editar_exposicao_motivos(request, ppc_id):
    ppc = get_object_or_404(PPC, id=ppc_id)
    if request.method == 'POST':
        form = ExposicaoMotivosForm(request.POST, instance=ppc)
        if form.is_valid():
            form.save()
            _consumir_campos_rascunho(request, ppc, ExposicaoMotivosForm)
            return redirect('editar_exposicao_motivos', ppc_id=ppc.id)
    else:
        form = ExposicaoMotivosForm(instance=ppc, initial=_initial_rascunho(request, ppc, ExposicaoMotivosForm))
    return render(request, 'ppc/editar_exposicao_motivos.html', {'form': form, 'ppc': ppc})

@staff_member_required(login_url='login')
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
    total_cursos = Curso.objects.count()
    total_ppcs = PPC.objects.count()
    ppcs_recentes = PPC.objects.select_related('curso').order_by('-atualizado_em')[:5]
    return render(request, "ppc/home.html", {
        'total_cursos': total_cursos,
        'total_ppcs': total_ppcs,
        'ppcs_recentes': ppcs_recentes,
    })

def ajuda(request):
    return render(request, 'ppc/ajuda.html')

@staff_member_required
def gestao_usuarios(request):
    query = request.GET.get('q', '')
    usuarios = User.objects.all().order_by('username')
    if query:
        usuarios = usuarios.filter(
            Q(username__icontains=query) | Q(email__icontains=query)
        )
    return render(request, 'ppc/gestao_usuarios.html', {'usuarios': usuarios, 'query': query})

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
        form = InformacoesGeraisForm(request.POST, curso=curso)
        if form.is_valid():
            ppc = form.save(commit=False)  # não salva ainda
            ppc.curso = curso              # completa o campo que faltava
            ppc.save()                     # agora sim salva
            return redirect('editar_apresentacao', ppc_id=ppc.id)
    else:
        form = InformacoesGeraisForm()
    return render(request, 'ppc/criar_ppc.html', {'form': form, 'curso': curso})


@login_required
def editar_objetivos(request, ppc_id):
    ppc = get_object_or_404(PPC, id=ppc_id)
    if request.method == 'POST':
        form = ObjetivosForm(request.POST, instance=ppc)
        if form.is_valid():
            form.save()
            _consumir_campos_rascunho(request, ppc, ObjetivosForm)
            return redirect('editar_objetivos', ppc_id=ppc.id)
    else:
        form = ObjetivosForm(instance=ppc, initial=_initial_rascunho(request, ppc, ObjetivosForm))
    return render(request, 'ppc/editar_objetivos.html', {'form': form, 'ppc': ppc})


@login_required
def gerar_pdf_ppc(request, ppc_id):
    """Gera uma representação de impressão independente das telas de edição."""
    bibliografias = Bibliografia.objects.order_by('tipo', 'autores', 'titulo')
    relacoes = RelacaoComponente.objects.select_related('componente_relacionado').order_by(
        'tipo', 'componente_relacionado__nome'
    )
    componentes = ComponenteCurricular.objects.order_by('periodo', 'nome').prefetch_related(
        Prefetch('bibliografias', queryset=bibliografias),
        Prefetch('relacoes', queryset=relacoes),
    )
    ppc = get_object_or_404(
        PPC.objects.select_related('curso').prefetch_related(
            Prefetch('componentes_curriculares', queryset=componentes),
            Prefetch('apendices', queryset=Apendice.objects.order_by('tipo', 'titulo')),
        ),
        id=ppc_id,
    )

    # A relação é opcional: PPCs presenciais não precisam ter DinamicaEAD.
    dinamica_ead = DinamicaEAD.objects.filter(ppc=ppc).first()
    html = render_to_string('ppc/pdf/ppc_documento.html', {
        'ppc': ppc,
        'componentes': ppc.componentes_curriculares.all(),
        'dinamica_ead': dinamica_ead,
    }, request=request)

    pdf = HTML(string=html, base_url=request.build_absolute_uri('/')).write_pdf()
    nome = slugify(ppc.curso.nome) or f'ppc-{ppc.pk}'
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="ppc-{nome}.pdf"'
    return response
