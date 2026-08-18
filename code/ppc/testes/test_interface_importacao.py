"""Testes sem rede para a escolha e os dois fluxos de importação."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.sessions.middleware import SessionMiddleware
from django.core.files.uploadedfile import SimpleUploadedFile
from django.middleware.csrf import CsrfViewMiddleware
from django.test import RequestFactory, SimpleTestCase

from ppc.forms import ImportarPPCModeloAntigoForm
from ppc.importacao_modelos_antigos import ErroImportacaoPPC
from ppc.forms import InformacoesGeraisForm
from ppc.views import _initial_rascunho, escolher_importacao_ppc, importar_ppc_modelo_antigo, importar_ppc_modelo_novo


class InterfaceImportacaoTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.curso = SimpleNamespace(id=12, nome="Curso de Teste")
        self.ppc = SimpleNamespace(id=34)

    def _requisicao(self, dados=None, arquivos=None, *, ajax=True):
        payload = dict(dados or {})
        payload.update(arquivos or {})
        request = self.factory.post('/cursos/12/importar/modelo-antigo/', payload,
                                    HTTP_X_REQUESTED_WITH='XMLHttpRequest' if ajax else '')
        request.user = SimpleNamespace(is_authenticated=True, is_staff=False, username='teste')
        SessionMiddleware(lambda _request: None).process_request(request)
        return request

    def _arquivo_pdf(self):
        return SimpleUploadedFile('ppc.pdf', b'%PDF-1.4\nconteudo', content_type='application/pdf')

    def test_form_antigo_rejeita_arquivo_ausente_e_nao_pdf(self):
        self.assertFalse(ImportarPPCModeloAntigoForm({'codigo_ppc': 1}, {}).is_valid())
        formulario = ImportarPPCModeloAntigoForm({'codigo_ppc': 1}, {'arquivo': SimpleUploadedFile('texto.txt', b'texto')})
        self.assertFalse(formulario.is_valid())

    @patch('ppc.views.get_object_or_404')
    @patch('ppc.views.preparar_importacao_modelo_antigo')
    def test_get_escolha_nao_inicia_importacao(self, preparar, busca_curso):
        busca_curso.return_value = self.curso
        request = self.factory.get('/cursos/12/importar/')
        request.user = SimpleNamespace(is_authenticated=True, is_staff=False, username='teste')
        resposta = escolher_importacao_ppc(request, 12)
        conteudo = resposta.content.decode()
        self.assertEqual(resposta.status_code, 200)
        self.assertIn('PPC Modelo Novo', conteudo)
        self.assertIn('PPC Modelo Antigo', conteudo)
        self.assertNotIn('painel-processamento', conteudo)
        preparar.assert_not_called()

    @patch('ppc.views.get_object_or_404')
    @patch('ppc.views.preparar_importacao_modelo_antigo')
    def test_get_modelo_antigo_esta_pronto_sem_loading_ou_pipeline(self, preparar, busca_curso):
        busca_curso.return_value = self.curso
        request = self.factory.get('/cursos/12/importar/modelo-antigo/')
        request.user = SimpleNamespace(is_authenticated=True, is_staff=False, username='teste')
        resposta = importar_ppc_modelo_antigo(request, 12)
        conteudo = resposta.content.decode()
        self.assertIn('Pronto para importar', conteudo)
        self.assertIn('hidden', conteudo)
        preparar.assert_not_called()

    def test_post_sem_csrf_e_rejeitado_pelo_middleware(self):
        request = self.factory.post('/cursos/12/importar/modelo-antigo/', {'codigo_ppc': 34})
        request.user = SimpleNamespace(is_authenticated=True)
        resposta = CsrfViewMiddleware(lambda _request: None).process_view(request, importar_ppc_modelo_antigo, (), {'curso_id': 12})
        self.assertEqual(resposta.status_code, 403)

    @patch('ppc.views.get_object_or_404')
    @patch('ppc.views.PPC.objects.filter')
    def test_codigo_antigo_inexistente_retorna_404(self, filtro, busca_curso):
        busca_curso.return_value = self.curso
        filtro.return_value.first.return_value = None
        resposta = importar_ppc_modelo_antigo(self._requisicao({'codigo_ppc': 999}, {'arquivo': self._arquivo_pdf()}), 12)
        self.assertEqual(resposta.status_code, 404)

    @patch('ppc.views.get_object_or_404')
    @patch('ppc.views.PPC.objects.filter')
    @patch('ppc.views.preparar_importacao_modelo_antigo')
    def test_modelo_antigo_prepara_rascunho_sem_salvar_e_redireciona_ppc_correto(self, preparar, filtro, busca_curso):
        busca_curso.return_value = self.curso
        filtro.return_value.first.return_value = self.ppc
        dados = {'curso': {}, 'ppc': {'apresentacao_texto': 'texto'}, 'componentes_curriculares': []}
        preparar.return_value = (dados, {'pronto_para_revisao': True}, {'estrategia': 'uma_chamada'})
        request = self._requisicao({'codigo_ppc': 34}, {'arquivo': self._arquivo_pdf()})
        resposta = importar_ppc_modelo_antigo(request, 12)
        corpo = json.loads(resposta.content)
        self.assertTrue(corpo['ok'])
        self.assertEqual(corpo['redirect_url'], '/ppc/34/informacoes-gerais/')
        self.assertEqual(request.session['rascunho_importacao_antiga_34']['dados'], dados)
        self.assertNotIn('importacao_antiga_em_andamento_12_34', request.session)

    @patch('ppc.views.get_object_or_404')
    @patch('ppc.views.PPC.objects.filter')
    @patch('ppc.views.preparar_importacao_modelo_antigo', side_effect=ErroImportacaoPPC('OpenRouter timeout 504'))
    def test_erro_antigo_nao_deixa_importacao_fantasma(self, _preparar, filtro, busca_curso):
        busca_curso.return_value = self.curso
        filtro.return_value.first.return_value = self.ppc
        request = self._requisicao({'codigo_ppc': 34}, {'arquivo': self._arquivo_pdf()})
        resposta = importar_ppc_modelo_antigo(request, 12)
        corpo = json.loads(resposta.content)
        self.assertEqual(resposta.status_code, 422)
        self.assertIn('demorou', corpo['erro'])
        self.assertNotIn('importacao_antiga_em_andamento_12_34', request.session)

    @patch('ppc.views.get_object_or_404')
    @patch('ppc.views.extrair_dados_pdf')
    @patch('ppc.views.PPC.objects.create')
    def test_modelo_novo_usa_exclusivamente_fluxo_legado(self, criar, extrair, busca_curso):
        busca_curso.return_value = self.curso
        extrair.return_value = {'modalidade': 'presencial', 'grau_academico': 'bacharelado', 'tipo_ppc': 'novo'}
        criar.return_value = SimpleNamespace(id=56)
        request = self.factory.post('/cursos/12/importar/modelo-novo/', {'arquivo': self._arquivo_pdf()})
        request.user = SimpleNamespace(is_authenticated=True, is_staff=False, username='teste')
        resposta = importar_ppc_modelo_novo(request, 12)
        self.assertEqual(resposta.status_code, 302)
        extrair.assert_called_once()
        self.assertEqual(resposta.url, '/ppc/56/informacoes-gerais/')

    def test_rascunho_alimenta_informacoes_sem_tocar_no_banco_e_nao_vaza_para_outro_ppc(self):
        request = self.factory.get('/ppc/34/informacoes-gerais/')
        SessionMiddleware(lambda _request: None).process_request(request)
        request.session['rascunho_importacao_antiga_34'] = {'dados': {'ppc': {'modalidade': 'ead', 'turno_funcionamento': 'Noturno'}}}
        ppc_a, ppc_b = SimpleNamespace(id=34), SimpleNamespace(id=35)
        inicial_a = _initial_rascunho(request, ppc_a, InformacoesGeraisForm)
        inicial_b = _initial_rascunho(request, ppc_b, InformacoesGeraisForm)
        self.assertEqual(inicial_a['modalidade'], 'ead')
        self.assertEqual(inicial_a['turno_funcionamento'], 'Noturno')
        self.assertEqual(inicial_b, {})
