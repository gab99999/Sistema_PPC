import ast
import re
import shutil
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import User
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management import call_command, CommandError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse, get_resolver, URLPattern, URLResolver
from django.core.management import call_command

from .models import (
    Curso, PPC, ComponenteCurricular, ComponenteNaMatriz,
    RelacaoComponente, MatrizReferenciaCurricular,
    ComponenteNaMatrizReferencia, RelacaoComponenteReferencia,
    ReferenciaBibliografica, Bibliografia, BibliografiaReferencia,
    ImportacaoPendencia, EquivalenciaMatriz, EquivalenciaPPC, GrupoEquivalenciaComponentes, ItemEquivalencia,
    VinculoUsuarioCurso,
)
from .services.comparacao_bibliografias import calcular_operacoes_bibliografia
from .services.painel_bibliografias import resumo_pendencias_bibliograficas
from .services.equivalencias_matrizes import consultar_equivalencias_matriz, salvar_equivalencias_matriz, preparar_editor_equivalencias
from .services.regras_equivalencia import avaliar_equivalencia, carga_total_segura


class DestaquesCKEditorTests(TestCase):
    def test_configuracao_tem_dezesseis_destaques_com_classes_e_modelos_unicos(self):
        opcoes = settings.CKEDITOR_5_CONFIGS["default"]["highlight"]["options"]

        self.assertIn("highlight", settings.CKEDITOR_5_CONFIGS["default"]["toolbar"])
        self.assertEqual(len(opcoes), 16)
        self.assertEqual(len({opcao["model"] for opcao in opcoes}), 16)
        self.assertEqual(len({opcao["class"] for opcao in opcoes}), 16)
        css = Path(__file__).parent / "static" / "ppc" / "highlights.css"
        conteudo_css = css.read_text(encoding="utf-8")
        self.assertEqual(sum(1 for opcao in opcoes if opcao["class"] in conteudo_css), 16)

    def test_formatacao_sem_mudar_texto_mantem_revisao_e_historico_sem_evento_de_edicao(self):
        from .completude import calcular_completude_ppc, confirmar_revisao
        from .models import EventoEdicao

        usuario = User.objects.create_user("revisor-destaque", password="x")
        curso = Curso.objects.create(
            nome="Curso destaques", unidade_academica="UA", area_conhecimento="Área",
        )
        ppc = PPC.objects.create(
            curso=curso, tipo_ppc="novo", modalidade="presencial",
            grau_academico="bacharelado", turno_funcionamento="Integral",
            numero_vagas_anuais=30, duracao_minima_semestres=4,
            duracao_media_semestres=6, duracao_maxima_semestres=8,
            diretor="D", vice_diretor="VD", coordenador_curso="C",
            vice_coordenador_curso="VC", apresentacao_texto="<p>Texto revisado.</p>",
        )
        confirmar_revisao(ppc, ["apresentacao"], usuario)
        eventos_antes = EventoEdicao.objects.filter(modelo="ppc.PPC", objeto_id=ppc.pk).count()
        historicos_antes = ppc.history.count()

        ppc.apresentacao_texto = '<p><mark class="hl-preto-vermelho">Texto revisado.</mark></p>'
        ppc.save(update_fields=["apresentacao_texto"])

        ppc.refresh_from_db()
        secao = next(
            item for item in calcular_completude_ppc(ppc)
            if item["chave"] == "apresentacao"
        )
        self.assertEqual(secao["estado"], "revisada")
        self.assertEqual(ppc.history.count(), historicos_antes + 1)
        self.assertEqual(
            EventoEdicao.objects.filter(modelo="ppc.PPC", objeto_id=ppc.pk).count(),
            eventos_antes,
        )


class ImportacoesInstitucionaisTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user("importador-staff", password="x", is_staff=True)
        self.usuario = User.objects.create_user("importador-nde", password="x", is_staff=False)
        self.url = reverse("importacoes_institucionais")

    def arquivo(self, nome="matriz.xlsx", conteudo=b"conteudo"):
        return SimpleUploadedFile(nome, conteudo)

    def test_acesso_anomimo_redireciona_nao_staff_recebe_403_e_staff_acessa(self):
        resposta = self.client.get(self.url)
        self.assertEqual(resposta.status_code, 302)
        self.assertIn(reverse("login"), resposta.url)

        self.client.force_login(self.usuario)
        self.assertEqual(self.client.get(self.url).status_code, 403)

        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_extensao_e_tamanho_sao_validados_antes_de_guardar_temporario(self):
        from .forms import ImportacaoArquivoForm
        from django.test import override_settings

        form_extensao = ImportacaoArquivoForm(
            {}, {"importar_matriz_referencia-arquivo": self.arquivo("matriz.csv")},
            comando="importar_matriz_referencia", prefix="importar_matriz_referencia",
        )
        self.assertFalse(form_extensao.is_valid())
        self.assertIn("Extensão inválida", str(form_extensao.errors))

        with override_settings(IMPORTACAO_TAMANHO_MAXIMO_MB=1):
            form_tamanho = ImportacaoArquivoForm(
                {}, {"importar_matriz_referencia-arquivo": self.arquivo("matriz.xlsx", b"x" * (1024 * 1024 + 1))},
                comando="importar_matriz_referencia", prefix="importar_matriz_referencia",
            )
            self.assertFalse(form_tamanho.is_valid())
            self.assertIn("excede o limite", str(form_tamanho.errors))

    @patch("ppc.views.os.rename", side_effect=lambda origem, destino: (shutil.copyfile(origem, destino), Path(origem).unlink()))
    @patch("ppc.views.executar_importacao")
    def test_matriz_exige_simulacao_mesmo_hash_token_unico_e_registra_eventos(self, executar, _renomear):
        from .models import EventoUso
        executar.side_effect = [
            {"sucesso": True, "saida": "Simulação sem gravação", "erro": "", "duracao": 0.25},
            {"sucesso": True, "saida": "Gravado", "erro": "", "duracao": 0.5},
        ]
        self.client.force_login(self.staff)
        dados = {
            "comando": "importar_matriz_referencia",
            "acao": "simular",
            "importar_matriz_referencia-arquivo": self.arquivo(),
        }
        resposta = self.client.post(self.url, dados)
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Simulação pronta")
        self.assertEqual(EventoUso.objects.filter(tipo="importacao", metadados__modo="simulacao").count(), 1)
        pendencia = self.client.session["ppc_importacao_pendente"]
        caminho = Path(pendencia["caminho"])
        self.assertTrue(caminho.is_file())

        confirmar = self.client.post(self.url, {
            "comando": "importar_matriz_referencia", "acao": "confirmar",
            "token": pendencia["token"],
        })
        self.assertEqual(confirmar.status_code, 200)
        self.assertContains(confirmar, "Operação concluída")
        self.assertFalse(caminho.exists())
        self.assertEqual(EventoUso.objects.filter(tipo="importacao", metadados__modo="confirmado").count(), 1)
        self.assertEqual(executar.call_count, 2)
        self.assertEqual(executar.call_args_list[0].args[2], "simulacao")
        self.assertEqual(executar.call_args_list[1].args[2], "confirmado")

        replay = self.client.post(self.url, {
            "comando": "importar_matriz_referencia", "acao": "confirmar",
            "token": pendencia["token"],
        })
        self.assertContains(replay, "simule novamente")
        self.assertEqual(executar.call_count, 2)

    @patch("ppc.views.executar_importacao")
    def test_temporario_ausente_exige_novo_upload_e_nao_executa_confirmacao(self, executar):
        executar.return_value = {"sucesso": True, "saida": "Simulado", "erro": "", "duracao": 0.1}
        self.client.force_login(self.staff)
        self.client.post(self.url, {
            "comando": "importar_matriz_referencia", "acao": "simular",
            "importar_matriz_referencia-arquivo": self.arquivo(),
        })
        pendencia = self.client.session["ppc_importacao_pendente"]
        Path(pendencia["caminho"]).unlink()
        resposta = self.client.post(self.url, {
            "comando": "importar_matriz_referencia", "acao": "confirmar",
            "token": pendencia["token"],
        })
        self.assertContains(resposta, "arquivo temporário não foi encontrado")
        self.assertEqual(executar.call_count, 1)

    @patch("ppc.views.os.rename", side_effect=PermissionError("rename indisponível"))
    @patch("ppc.views.executar_importacao")
    def test_falha_na_renomeacao_nao_executa_confirmacao(self, executar, _renomear):
        executar.return_value = {"sucesso": True, "saida": "Simulado", "erro": "", "duracao": 0.1}
        self.client.force_login(self.staff)
        self.client.post(self.url, {
            "comando": "importar_matriz_referencia", "acao": "simular",
            "importar_matriz_referencia-arquivo": self.arquivo(),
        })
        pendencia = self.client.session["ppc_importacao_pendente"]
        resposta = self.client.post(self.url, {
            "comando": "importar_matriz_referencia", "acao": "confirmar",
            "token": pendencia["token"],
        })
        self.assertContains(resposta, "não está disponível para confirmação")
        self.assertEqual(executar.call_count, 1)
        self.assertFalse(Path(pendencia["caminho"]).exists())

    @patch("ppc.views.executar_importacao")
    def test_comando_direto_exige_checkbox_e_saida_e_escapada(self, executar):
        from .models import CineBrasilCurso, EventoUso
        self.client.force_login(self.staff)
        arquivo_csv = SimpleUploadedFile(
            "cine.csv",
            b"nome_curso,area_geral_codigo,rotulo_codigo,area_geral_nome,rotulo_nome\nCurso Teste,01,011,Area,Rotulo\n",
        )
        sem_confirmacao = self.client.post(self.url, {
            "comando": "importar_cine_brasil", "acao": "executar_direto",
            "importar_cine_brasil-arquivo": arquivo_csv,
        })
        self.assertContains(sem_confirmacao, "Marque a confirmação")
        executar.assert_not_called()
        self.assertFalse(CineBrasilCurso.objects.exists())

        executar.return_value = {"sucesso": True, "saida": "<script>alert(1)</script>", "erro": "", "duracao": 0.3}
        resposta = self.client.post(self.url, {
            "comando": "importar_cine_brasil", "acao": "executar_direto",
            "importar_cine_brasil-arquivo": SimpleUploadedFile("cine.csv", b"conteudo"),
            "importar_cine_brasil-confirmacao_explicita": "on",
        })
        self.assertContains(resposta, "&lt;script&gt;alert(1)&lt;/script&gt;")
        self.assertNotContains(resposta, "<script>alert(1)</script>")
        self.assertEqual(EventoUso.objects.filter(tipo="importacao", metadados__modo="confirmado").count(), 1)

    def test_cine_brasil_executa_com_call_command_mede_tempo_e_avisa_repeticao(self):
        from .models import CineBrasilCurso, EventoUso

        self.client.force_login(self.staff)
        conteudo = (
            b"nome_curso,area_geral_codigo,rotulo_codigo,area_geral_nome,rotulo_nome\n"
            b"Curso CSV,01,011,Area geral,Rotulo\n"
        )
        dados = {
            "comando": "importar_cine_brasil", "acao": "executar_direto",
            "importar_cine_brasil-arquivo": SimpleUploadedFile("cine.csv", conteudo),
            "importar_cine_brasil-confirmacao_explicita": "on",
        }
        primeira = self.client.post(self.url, dados)
        self.assertContains(primeira, "Operação concluída em")
        self.assertContains(primeira, "1 criados")
        self.assertEqual(CineBrasilCurso.objects.count(), 1)
        evento = EventoUso.objects.get(tipo="importacao", metadados__comando="importar_cine_brasil")
        self.assertTrue(evento.metadados["sucesso"])
        self.assertGreaterEqual(evento.metadados["duracao_segundos"], 0)

        segunda = self.client.post(self.url, {
            **dados,
            "importar_cine_brasil-arquivo": SimpleUploadedFile("cine.csv", conteudo),
        })
        self.assertContains(segunda, "Este arquivo já foi importado")
        self.assertEqual(CineBrasilCurso.objects.count(), 1)

    def test_bibliografias_aparecem_indisponiveis_e_nao_podem_ser_executadas(self):
        self.client.force_login(self.staff)
        resposta = self.client.get(self.url)
        self.assertContains(resposta, "Bibliografias")
        self.assertContains(resposta, "ainda não é idempotente")
        with patch("ppc.views.executar_importacao") as executar:
            resposta = self.client.post(self.url, {
                "comando": "importar_bibliografias", "acao": "executar_direto",
                "importar_bibliografias-arquivo": self.arquivo("bibliografia.csv"),
                "importar_bibliografias-confirmacao_explicita": "on",
            })
            self.assertContains(resposta, "indisponível")
            executar.assert_not_called()

    def test_importador_matriz_reporta_codigo_duplicado_com_diferenca_de_caixa_e_espacos(self):
        from ppc.models import ComponenteCurricular

        ComponenteCurricular.objects.create(
            codigo="CUR-1", nome="Existente", tipo="disciplina",
            carga_horaria_teorica=64, carga_horaria_pratica=0,
            carga_horaria_estudante=0, carga_horaria_professor=0,
            carga_horaria_acex=0, unidade_academica_componente="UA", ementa="",
        )
        linha = {
            "confianca": "determinada", "codigo": " cur-1 ",
            "id_componente_interno": None, "identificador_origem": "origem-teste",
            "periodo": 1, "natureza": "obrigatoria", "carga_horaria_teorica": 64,
            "carga_horaria_pratica": 0, "nome": "Novo", "ementa": "Ementa",
            "nucleo": "NC", "linha_origem": 2,
        }
        stdout, stderr = StringIO(), StringIO()
        with patch(
            "ppc.management.commands.importar_matriz_referencia.normalizar_planilha_matriz",
            return_value=[linha],
        ), self.assertRaises(CommandError) as erro:
            call_command(
                "importar_matriz_referencia", "arquivo.xlsx", confirmar=True,
                stdout=stdout, stderr=stderr,
            )
        self.assertIn("importação parcial", str(erro.exception).lower())
        self.assertIn("maiúsculas", stderr.getvalue())
        self.assertNotIn("Importação concluída e gravada", stdout.getvalue())
        self.assertEqual(ComponenteCurricular.objects.count(), 1)


class RegraCentralEquivalenciaTests(TestCase):
    def setUp(self):
        self.curso = Curso.objects.create(nome="Curso regra", unidade_academica="UA", area_conhecimento="Área")
        self.matriz_antiga = MatrizReferenciaCurricular.objects.create(curso=self.curso, nome="Antiga")
        self.matriz_nova = MatrizReferenciaCurricular.objects.create(curso=self.curso, nome="Nova", matriz_anterior=self.matriz_antiga)

    def item(self, matriz, nome, *, acex=0, ementa="Texto", tipo="disciplina", estudante=None, teoria=64):
        componente = ComponenteCurricular.objects.create(
            nome=nome, codigo="", tipo=tipo, carga_horaria_teorica=teoria,
            carga_horaria_pratica=0, carga_horaria_estudante=estudante,
            carga_horaria_professor=0, carga_horaria_acex=acex, ementa=ementa,
        )
        return ComponenteNaMatrizReferencia.objects.create(
            matriz=matriz, componente=componente, periodo=1, natureza="obrigatoria",
        )

    def test_acex_insuficiente_rejeita_e_ementa_nao_e_condicao_de_validade(self):
        anterior = self.item(self.matriz_antiga, "Antiga", acex=8, ementa="Ementa diferente")
        nova = self.item(self.matriz_nova, "Nova", acex=16, ementa="Outra ementa")
        resultado = avaliar_equivalencia(anterior, nova)
        self.assertFalse(resultado["elegivel"])
        self.assertIn("ACEx insuficiente", " ".join(resultado["motivos"]))
        nova.componente.carga_horaria_acex = 8
        nova.componente.save()
        resultado = avaliar_equivalencia(anterior, nova)
        self.assertTrue(resultado["elegivel"])
        self.assertFalse(resultado["sugestao_automatica"])

    def test_ementa_normalizada_sugere_e_acex_zero_aceita_anterior_sem_acex(self):
        anterior = self.item(self.matriz_antiga, "Antiga", acex=None, ementa="cafe\u0301   com leite")
        nova = self.item(self.matriz_nova, "Nova", acex=0, ementa="café com leite")
        resultado = avaliar_equivalencia(anterior, nova)
        self.assertTrue(resultado["elegivel"])
        self.assertTrue(resultado["sugestao_automatica"])

    def test_atividade_sem_ch_estudante_e_incompleta_sem_lancar_typeerror(self):
        componente = ComponenteCurricular.objects.create(
            nome="Atividade sem estudante", tipo="atividade", carga_horaria_teorica=0,
            carga_horaria_pratica=0, carga_horaria_estudante=None,
            carga_horaria_professor=0, carga_horaria_acex=0, ementa="",
        )
        ch, motivo = carga_total_segura(componente)
        self.assertIsNone(ch)
        self.assertIn("Carga horária incompleta", motivo)

    def test_clean_matriz_valida_acex_sem_exigir_ementa_e_alerta_par_legado(self):
        anterior = self.item(self.matriz_antiga, "Antiga", acex=8, ementa="Ementa A")
        nova = self.item(self.matriz_nova, "Nova", acex=8, ementa="Ementa B")
        par = EquivalenciaMatriz(item_novo=nova, item_anterior=anterior)
        par.clean()
        par.save()
        ComponenteCurricular.objects.filter(pk=nova.componente_id).update(carga_horaria_acex=16)
        par_legado = EquivalenciaMatriz.objects.get(item_novo=nova, item_anterior=anterior)
        dados = preparar_editor_equivalencias(self.matriz_nova)
        self.assertEqual(len(dados["legadas_invalidas"]), 1)
        self.assertIn("ACEx insuficiente", dados["legadas_invalidas"][0]["motivo"])

    def test_clean_equivalencia_ppc_usa_regra_de_acex_e_preserva_validacao_de_cadeia(self):
        anterior_ppc = PPC.objects.create(curso=self.curso, tipo_ppc="novo", modalidade="presencial", grau_academico="bacharelado", turno_funcionamento="Integral", numero_vagas_anuais=30, duracao_minima_semestres=4, duracao_media_semestres=6, duracao_maxima_semestres=8, diretor="D", vice_diretor="VD", coordenador_curso="C", vice_coordenador_curso="VC")
        novo_ppc = PPC.objects.create(curso=self.curso, ppc_anterior=anterior_ppc, tipo_ppc="reformulacao", modalidade="presencial", grau_academico="bacharelado", turno_funcionamento="Integral", numero_vagas_anuais=30, duracao_minima_semestres=4, duracao_media_semestres=6, duracao_maxima_semestres=8, diretor="D", vice_diretor="VD", coordenador_curso="C", vice_coordenador_curso="VC")
        velho_ref = self.item(self.matriz_antiga, "Velho", acex=8)
        novo_ref = self.item(self.matriz_nova, "Novo", acex=16)
        velho = ComponenteNaMatriz.objects.create(ppc=anterior_ppc, componente=velho_ref.componente, periodo=1, natureza="obrigatoria")
        novo = ComponenteNaMatriz.objects.create(ppc=novo_ppc, componente=novo_ref.componente, periodo=1, natureza="obrigatoria")
        with self.assertRaises(ValidationError) as erro:
            EquivalenciaPPC(item_novo=novo, item_anterior=velho).clean()
        self.assertIn("ACEx insuficiente", " ".join(erro.exception.messages))

    def test_nomes_de_evento_nao_excedem_limite_do_campo(self):
        import inspect
        from ppc.services import eventos
        from .models import EventoUso

        def strings_da_expressao(expressao):
            if isinstance(expressao, ast.Constant) and isinstance(expressao.value, str):
                return [expressao.value]
            if isinstance(expressao, ast.IfExp):
                return strings_da_expressao(expressao.body) + strings_da_expressao(expressao.orelse)
            return []

        raiz = Path(inspect.getfile(eventos)).resolve().parents[1]
        nomes = []
        for arquivo in raiz.rglob("*.py"):
            if "migrations" in arquivo.parts or "testes" in arquivo.parts or arquivo.name == "tests.py":
                continue
            arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
            for no in ast.walk(arvore):
                if isinstance(no, ast.Call) and isinstance(no.func, ast.Name) and no.func.id == "registrar_evento" and no.args:
                    nomes.extend(strings_da_expressao(no.args[0]))
        limite = EventoUso._meta.get_field("tipo").max_length
        excedidos = [nome for nome in nomes if len(nome) > limite]
        self.assertTrue(nomes, "O teste não encontrou chamadas registrar_evento.")
        self.assertEqual(excedidos, [])


class ComponentesPendentesMatrizTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("criador-matriz", password="x")
        self.staff = User.objects.create_user("staff-matriz-a", password="x", is_staff=True)
        self.curso = Curso.objects.create(nome="Curso pendentes", unidade_academica="UA", area_conhecimento="Área")
        self.matriz = MatrizReferenciaCurricular.objects.create(
            curso=self.curso, nome="Matriz pendentes", status=MatrizReferenciaCurricular.STATUS_EM_MUDANCA,
        )
        VinculoUsuarioCurso.objects.create(usuario=self.user, curso=self.curso)

    def componente(self, nome, *, status="aprovado"):
        return ComponenteCurricular.objects.create(
            nome=nome, tipo="disciplina", carga_horaria_teorica=64,
            carga_horaria_pratica=0, carga_horaria_estudante=0,
            carga_horaria_professor=0, carga_horaria_acex=0, ementa="",
            status=status,
        )

    def ppc(self):
        return PPC.objects.create(
            curso=self.curso, tipo_ppc="novo", modalidade="presencial", grau_academico="bacharelado",
            turno_funcionamento="Integral", numero_vagas_anuais=30,
            duracao_minima_semestres=4, duracao_media_semestres=6, duracao_maxima_semestres=8,
            diretor="D", vice_diretor="VD", coordenador_curso="C", vice_coordenador_curso="VC",
        )

    def test_form_define_status_e_criador_no_servidor_e_nao_expoe_status(self):
        from .forms import ComponenteMatrizReferenciaForm
        form_vazio = ComponenteMatrizReferenciaForm(matriz=self.matriz)
        self.assertNotIn("codigo", form_vazio.fields)
        self.assertNotIn("ccu", form_vazio.fields)
        dados = {
            "codigo": "COD-ENVIADO", "nome": "Pendente novo", "tipo": "disciplina", "ccu": "True",
            "carga_horaria_teorica": "64", "carga_horaria_pratica": "0",
            "carga_horaria_estudante": "", "carga_horaria_professor": "", "carga_horaria_acex": "0",
            "ementa": "Ementa teste", "nucleo": "NE", "natureza": "obrigatoria", "periodo": "1",
            "grupo_licenciatura": "", "status": "aprovado",
        }
        form = ComponenteMatrizReferenciaForm(dados, matriz=self.matriz)
        self.assertNotIn("status", form.fields)
        self.assertTrue(form.is_valid(), form.errors)
        form.salvar_na_matriz(self.matriz, self.user)
        pendente = ComponenteCurricular.objects.get(nome="Pendente novo")
        self.assertEqual(pendente.status, "pendente")
        self.assertEqual(pendente.criado_por, self.user)
        self.assertEqual(pendente.codigo, "")
        self.assertIsNone(pendente.ccu)
        dados["nome"] = "Aprovado staff"
        form_staff = ComponenteMatrizReferenciaForm(dados, matriz=self.matriz)
        self.assertTrue(form_staff.is_valid(), form_staff.errors)
        form_staff.salvar_na_matriz(self.matriz, self.staff)
        aprovado = ComponenteCurricular.objects.get(nome="Aprovado staff")
        self.assertEqual(aprovado.status, "aprovado")
        self.assertEqual(aprovado.criado_por, self.staff)

    def test_post_matriz_ignora_codigo_e_ccu_enviados(self):
        self.client.force_login(self.staff)
        resposta = self.client.post(
            reverse("criar_componente_matriz_referencia", args=[self.matriz.pk]),
            {
                "codigo": "COD-NAO-GRAVAR", "ccu": "True", "nome": "POST sem campos",
                "tipo": "disciplina", "carga_horaria_teorica": "64",
                "carga_horaria_pratica": "0", "carga_horaria_estudante": "",
                "carga_horaria_professor": "", "carga_horaria_acex": "0", "ementa": "Ementa",
                "nucleo": "NE", "natureza": "obrigatoria", "periodo": "1",
            },
        )
        self.assertEqual(resposta.status_code, 302)
        componente = ComponenteCurricular.objects.get(nome="POST sem campos")
        self.assertEqual(componente.codigo, "")
        self.assertIsNone(componente.ccu)
        self.assertEqual(componente.status, "aprovado")
        self.assertEqual(componente.criado_por, self.staff)

    def test_busca_da_matriz_inclui_pendente_com_selo_e_ambas_as_filas(self):
        pendente = self.componente("Pendente visível", status="pendente")
        pendente.criado_por = self.user
        pendente.save(update_fields=["criado_por"])
        ComponenteNaMatrizReferencia.objects.create(
            matriz=self.matriz, componente=pendente, periodo=1, natureza="obrigatoria",
        )
        busca_pendente = self.componente("Pendente busca", status="pendente")
        busca_pendente.criado_por = self.user
        busca_pendente.save(update_fields=["criado_por"])
        self.client.force_login(self.staff)
        busca = self.client.get(reverse("buscar_componente_existente_matriz_referencia", args=[self.matriz.pk]), {"q": "Pendente busca"})
        self.assertContains(busca, "Aguardando aprovação")
        self.assertContains(busca, "Pendente busca")
        self.assertContains(self.client.get(reverse("matriz_referencia_detalhe", args=[self.matriz.pk])), "Status do catálogo")
        self.assertContains(self.client.get(reverse("matriz_referencia_detalhe", args=[self.matriz.pk])), "Aguardando aprovação")
        self.assertContains(self.client.get(reverse("fila_aprovacao_componentes")), "Pendente visível")
        self.client.force_login(self.user)
        self.assertContains(self.client.get(reverse("meus_componentes_pendentes")), "Pendente visível")
        self.assertEqual(pendente.criado_por, self.user)

    def test_aplicacao_lista_e_ignora_pendente_e_adicao_existente_ao_ppc_retorna_403(self):
        ppc = self.ppc()
        pendente = self.componente("Pendente na matriz", status="pendente")
        ComponenteNaMatrizReferencia.objects.create(matriz=self.matriz, componente=pendente, periodo=1, natureza="obrigatoria")
        self.client.force_login(self.staff)
        url = reverse("preview_aplicar_matriz_referencia", args=[ppc.pk, self.matriz.pk])
        preview = self.client.get(url)
        self.assertContains(preview, "aguardando aprovação")
        self.assertEqual(preview.context["preview"]["componentes_pendentes"][0].componente_id, pendente.pk)
        self.assertFalse(preview.context["preview"]["novos"])
        resultado = self.client.post(url)
        self.assertContains(resultado, "não foram copiados")
        self.assertFalse(ComponenteNaMatriz.objects.filter(ppc=ppc, componente=pendente).exists())
        resposta = self.client.get(reverse("adicionar_componente_existente", args=[ppc.pk, pendente.pk]))
        self.assertEqual(resposta.status_code, 403)
        pendente.status = "aprovado"
        pendente.save(update_fields=["status"])
        preview = self.client.get(url)
        item = preview.context["preview"]["novos"][0]
        self.client.post(url, {f"aplicar_novo_{item.pk}": "on"})
        self.assertTrue(ComponenteNaMatriz.objects.filter(ppc=ppc, componente=pendente).exists())


class SugestoesComponentesMatrizTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("sugestao-editor", password="x")
        self.sem_acesso = User.objects.create_user("sugestao-leitor", password="x")
        self.curso = Curso.objects.create(nome="Curso sugestões", unidade_academica="UA", area_conhecimento="Área")
        self.matriz = MatrizReferenciaCurricular.objects.create(
            curso=self.curso, nome="Matriz sugestões", status=MatrizReferenciaCurricular.STATUS_EM_MUDANCA,
        )
        VinculoUsuarioCurso.objects.create(usuario=self.user, curso=self.curso)
        self.url = reverse("sugerir_componentes_matriz_referencia", args=[self.matriz.pk])

    def componente(self, nome, *, codigo="", status="aprovado"):
        return ComponenteCurricular.objects.create(
            nome=nome, codigo=codigo, tipo="disciplina", carga_horaria_teorica=64,
            carga_horaria_pratica=0, ementa="", status=status,
        )

    def test_endpoint_devolve_json_403_sem_permissao(self):
        self.client.force_login(self.sem_acesso)
        response = self.client.get(self.url, {"nome": "catalogo"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response["Content-Type"], "application/json")

    def test_minimo_tres_caracteres_e_busca_sem_acento(self):
        self.componente("Café Avançado")
        self.client.force_login(self.user)
        curta = self.client.get(self.url, {"nome": "ca"}).json()
        self.assertTrue(curta["nome_minimo"])
        self.assertEqual(curta["itens"], [])
        completa = self.client.get(self.url, {"nome": "cafe avancado"}).json()
        self.assertEqual(completa["itens"][0]["nome"], "Café Avançado")
        from .forms import ComponenteMatrizReferenciaForm
        form = ComponenteMatrizReferenciaForm({
            "codigo": "", "nome": "Cafe avancado novo", "tipo": "disciplina", "ccu": "",
            "carga_horaria_teorica": "64", "carga_horaria_pratica": "0",
            "carga_horaria_estudante": "", "carga_horaria_professor": "", "carga_horaria_acex": "0",
            "ementa": "Teste", "nucleo": "NE", "natureza": "obrigatoria", "periodo": "1",
            "grupo_licenciatura": "",
        }, matriz=self.matriz)
        self.assertTrue(form.is_valid(), form.errors)  # sugestão não impede criação

    def test_limite_cinco_pendente_com_status_e_codigo_igual(self):
        for indice in range(7):
            self.componente(f"Biologia Molecular {indice}", status="pendente" if indice == 0 else "aprovado")
        existente = self.componente("Código já cadastrado", codigo=" AdAs ")
        self.client.force_login(self.user)
        response = self.client.get(self.url, {"nome": "biologia molecular", "codigo": "adas"}).json()
        self.assertEqual(len(response["itens"]), 5)
        self.assertTrue(response["codigo_igual"])
        codigo_item = next(item for item in response["itens"] if item["id"] == existente.pk)
        self.assertTrue(codigo_item["codigo_igual"])
        pending = self.client.get(self.url, {"nome": "biologia molecular 0"}).json()
        self.assertTrue(any(item["status"] == "pendente" for item in pending["itens"]))

    def test_validacao_codigo_novo_duplicado_legado_inalterado_e_vazios(self):
        existente = self.componente("Código existente", codigo=" AdAs ")
        with self.assertRaises(ValidationError):
            self.componente("Duplicado", codigo="adas")
        # Simula duplicatas legadas pré-existentes sem passar pelo save validado.
        legado = ComponenteCurricular(
            nome="Legado 2", codigo="ADAS", tipo="disciplina", carga_horaria_teorica=64,
            carga_horaria_pratica=0, ementa="",
        )
        ComponenteCurricular.objects.bulk_create([legado])
        # MySQL pode não preencher o PK dos objetos passados a bulk_create.
        legado = ComponenteCurricular.objects.get(nome="Legado 2")
        legado.nome = "Legado editado"
        legado.save()
        legado.status = "pendente"
        legado.save(update_fields=["status"])
        self.client.force_login(User.objects.create_user("staff-aprovador", password="x", is_staff=True))
        resposta = self.client.post(reverse("aprovar_componente", args=[legado.pk]))
        self.assertEqual(resposta.status_code, 302)
        legado.refresh_from_db()
        self.assertEqual(legado.status, "aprovado")
        vazio1 = self.componente("Sem código 1")
        vazio2 = self.componente("Sem código 2")
        self.assertEqual(vazio1.codigo, "")
        self.assertEqual(vazio2.codigo, "")
        from .forms import CodigoComponenteForm
        form = CodigoComponenteForm({"componente_id": vazio1.pk, "codigo": "adas"})
        self.assertFalse(form.is_valid())


class AplicacaoEquivalenciasMatrizPpcTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("aplicacao-equivalencias", password="x", is_staff=True)
        self.curso = Curso.objects.create(nome="Curso aplicação equivalências", unidade_academica="UA", area_conhecimento="Área")
        self.matriz_anterior = MatrizReferenciaCurricular.objects.create(curso=self.curso, nome="Matriz anterior")
        self.matriz = MatrizReferenciaCurricular.objects.create(
            curso=self.curso, nome="Matriz nova", matriz_anterior=self.matriz_anterior,
        )
        self.ppc_antigo = self.novo_ppc("PPC antigo")
        self.ppc_anterior = self.novo_ppc("PPC anterior", ppc_anterior=self.ppc_antigo)
        self.ppc = self.novo_ppc("PPC atual", ppc_anterior=self.ppc_anterior)

    def novo_ppc(self, nome, ppc_anterior=None, curso=None):
        curso = curso or self.curso
        return PPC.objects.create(
            curso=curso, ppc_anterior=ppc_anterior, tipo_ppc="novo", modalidade="presencial",
            grau_academico="bacharelado", turno_funcionamento="Integral", numero_vagas_anuais=30,
            duracao_minima_semestres=4, duracao_media_semestres=6, duracao_maxima_semestres=8,
            diretor="D", vice_diretor="VD", coordenador_curso="C", vice_coordenador_curso="VC",
        )

    def componente(self, nome, *, acex=8, teoria=64, status="aprovado"):
        return ComponenteCurricular.objects.create(
            nome=nome, tipo="disciplina", carga_horaria_teorica=teoria,
            carga_horaria_pratica=0, carga_horaria_acex=acex, ementa="",
            status=status,
        )

    def par_matriz(self, nome, *, acex_novo=8, acex_antigo=8, ch_novo=64, ch_antigo=64, status="aprovado", legacy=False):
        novo_comp = self.componente(f"Novo {nome}", acex=acex_novo, teoria=ch_novo, status=status)
        antigo_comp = self.componente(f"Antigo {nome}", acex=acex_antigo, teoria=ch_antigo)
        novo_ref = ComponenteNaMatrizReferencia.objects.create(
            matriz=self.matriz, componente=novo_comp, periodo=1, natureza="obrigatoria",
        )
        antigo_ref = ComponenteNaMatrizReferencia.objects.create(
            matriz=self.matriz_anterior, componente=antigo_comp, periodo=1, natureza="obrigatoria",
        )
        par = EquivalenciaMatriz(item_novo=novo_ref, item_anterior=antigo_ref)
        if legacy:
            EquivalenciaMatriz.objects.bulk_create([par])
        else:
            par.save()
        return novo_ref, antigo_ref

    def vinculo(self, ppc, componente):
        return ComponenteNaMatriz.objects.create(
            ppc=ppc, componente=componente, periodo=1, natureza="obrigatoria",
        )

    def test_aplicacao_cria_par_preserva_existente_e_registra_contagens(self):
        novo_ref, antigo_ref = self.par_matriz("Novo")
        antigo = self.vinculo(self.ppc_anterior, antigo_ref.componente)
        self.vinculo(self.ppc_antigo, self.componente("Outro ancestral"))
        self.client.force_login(self.user)
        url = reverse("preview_aplicar_matriz_referencia", args=[self.ppc.pk, self.matriz.pk])
        preview = self.client.get(url)
        self.assertContains(preview, "Equivalências")
        self.assertContains(preview, 'name="aplicar_equivalencias"')
        self.assertContains(preview, "checked")
        response = self.client.post(url, {f"aplicar_novo_{novo_ref.pk}": "on", "aplicar_equivalencias": "on"})
        novo = ComponenteNaMatriz.objects.get(ppc=self.ppc, componente=novo_ref.componente)
        equivalencia = EquivalenciaPPC.objects.get(item_novo=novo, item_anterior=antigo)
        self.assertEqual(equivalencia.criado_por, self.user)
        evento = __import__("ppc.models", fromlist=["EventoUso"]).EventoUso.objects.filter(tipo="matriz_aplicada", ppc=self.ppc).latest("pk")
        self.assertEqual(evento.metadados["equivalencias_criadas"], 1)
        self.assertContains(response, "1 novas")
        # A reaplicação classifica o par como existente e não o substitui.
        response = self.client.post(url, {"aplicar_equivalencias": "on"})
        self.assertEqual(EquivalenciaPPC.objects.filter(item_novo=novo, item_anterior=antigo).count(), 1)
        self.assertContains(response, "já existentes")

    def test_caixa_desmarcada_nao_cria_e_post_recalcula_par_obsoleto(self):
        novo_ref, antigo_ref = self.par_matriz("Desmarcado")
        self.vinculo(self.ppc_anterior, antigo_ref.componente)
        self.client.force_login(self.user)
        url = reverse("preview_aplicar_matriz_referencia", args=[self.ppc.pk, self.matriz.pk])
        self.client.get(url)
        self.client.post(url, {f"aplicar_novo_{novo_ref.pk}": "on"})
        self.assertFalse(EquivalenciaPPC.objects.exists())

    def test_preview_e_resultado_da_aplicacao_sinalizam_acex_insuficiente(self):
        novo_ref, antigo_ref = self.par_matriz(
            "ACEx legado", acex_novo=16, acex_antigo=8, ch_novo=64, ch_antigo=80, legacy=True,
        )
        self.vinculo(self.ppc_anterior, antigo_ref.componente)
        self.client.force_login(self.user)
        url = reverse("preview_aplicar_matriz_referencia", args=[self.ppc.pk, self.matriz.pk])
        preview = self.client.get(url)
        self.assertEqual(preview.status_code, 200)
        self.assertContains(preview, "ACEx insuficiente: anterior 8 h, nova 16 h")
        self.assertContains(preview, "não aplicável(is)")

        resultado = self.client.post(url, {
            f"aplicar_novo_{novo_ref.pk}": "on", "aplicar_equivalencias": "on",
        })
        self.assertEqual(resultado.status_code, 200)
        self.assertContains(resultado, "ACEx insuficiente: anterior 8 h, nova 16 h")
        novo_ppc = ComponenteNaMatriz.objects.get(ppc=self.ppc, componente=novo_ref.componente)
        antigo_ppc = ComponenteNaMatriz.objects.get(ppc=self.ppc_anterior, componente=antigo_ref.componente)
        self.assertFalse(EquivalenciaPPC.objects.filter(item_novo=novo_ppc, item_anterior=antigo_ppc).exists())
        EquivalenciaMatriz.objects.filter(item_novo=novo_ref).delete()
        self.client.post(url, {f"aplicar_novo_{novo_ref.pk}": "on", "aplicar_equivalencias": "on"})
        self.assertFalse(EquivalenciaPPC.objects.exists())

    def test_service_lista_ch_acex_pendente_e_componente_anterior_fora_da_cadeia(self):
        from ppc.services.aplicacao_equivalencias import traduzir_equivalencias_matriz_para_ppc
        casos = (
            ("ACEx", dict(acex_novo=16, acex_antigo=8, legacy=True), "ACEx insuficiente"),
            ("CH", dict(ch_novo=80, ch_antigo=64, legacy=True), "CH total insuficiente"),
            ("Pendente", dict(status="pendente"), "componente aguardando aprovação"),
        )
        for nome, args, motivo in casos:
            novo_ref, antigo_ref = self.par_matriz(nome, **args)
            self.vinculo(self.ppc_anterior, antigo_ref.componente)
            resultado = traduzir_equivalencias_matriz_para_ppc(
                self.matriz, self.ppc, componentes_planejados={novo_ref.pk},
            )
            self.assertTrue(any(motivo in item["motivo"] for item in resultado["nao_aplicaveis"]))
        novo_ref, antigo_ref = self.par_matriz(
            "Par PPC legado já existente", acex_novo=16, acex_antigo=8,
            ch_novo=64, ch_antigo=80, legacy=True,
        )
        novo_ppc = self.vinculo(self.ppc, novo_ref.componente)
        antigo_ppc = self.vinculo(self.ppc_anterior, antigo_ref.componente)
        EquivalenciaPPC.objects.bulk_create([
            EquivalenciaPPC(item_novo=novo_ppc, item_anterior=antigo_ppc),
        ])
        resultado = traduzir_equivalencias_matriz_para_ppc(self.matriz, self.ppc)
        self.assertTrue(any("ACEx insuficiente" in item["motivo"] for item in resultado["nao_aplicaveis"]))
        self.assertTrue(EquivalenciaPPC.objects.filter(item_novo=novo_ppc, item_anterior=antigo_ppc).exists())
        novo_ref, antigo_ref = self.par_matriz("Fora cadeia")
        # O item anterior existe no catálogo, mas não em nenhum PPC ancestral.
        resultado = traduzir_equivalencias_matriz_para_ppc(
            self.matriz, self.ppc, componentes_planejados={novo_ref.pk},
        )
        self.assertTrue(any("não está na cadeia" in item["motivo"] for item in resultado["nao_aplicaveis"]))

    def test_service_lista_sem_predecessor_matriz_sem_curso_curso_divergente_e_ambiguidade(self):
        from ppc.services.aplicacao_equivalencias import traduzir_equivalencias_matriz_para_ppc
        novo_ref, antigo_ref = self.par_matriz("Sem anterior PPC")
        ppc_sem_anterior = self.novo_ppc("Sem anterior")
        resultado = traduzir_equivalencias_matriz_para_ppc(
            self.matriz, ppc_sem_anterior, componentes_planejados={novo_ref.pk},
        )
        self.assertTrue(any("PPC sem ppc_anterior" in item["motivo"] for item in resultado["nao_aplicaveis"]))

        curso_outro = Curso.objects.create(nome="Curso divergente", unidade_academica="UA", area_conhecimento="Área")
        matriz_sem_curso = MatrizReferenciaCurricular.objects.create(nome="Matriz sem curso")
        novo = self.componente("Matriz sem curso novo")
        velho = self.componente("Matriz sem curso velho")
        item_novo = ComponenteNaMatrizReferencia.objects.create(matriz=matriz_sem_curso, componente=novo, periodo=1, natureza="obrigatoria")
        item_velho = ComponenteNaMatrizReferencia.objects.create(matriz=self.matriz_anterior, componente=velho, periodo=1, natureza="obrigatoria")
        EquivalenciaMatriz.objects.bulk_create([EquivalenciaMatriz(item_novo=item_novo, item_anterior=item_velho)])
        resultado = traduzir_equivalencias_matriz_para_ppc(matriz_sem_curso, self.ppc)
        self.assertIn("matriz sem curso", resultado["nao_aplicaveis"][0]["motivo"])

        matriz_outro = MatrizReferenciaCurricular.objects.create(curso=curso_outro, nome="Matriz outro curso")
        novo_outro = ComponenteNaMatrizReferencia.objects.create(matriz=matriz_outro, componente=self.componente("Novo curso divergente"), periodo=1, natureza="obrigatoria")
        EquivalenciaMatriz.objects.bulk_create([EquivalenciaMatriz(item_novo=novo_outro, item_anterior=item_velho)])
        resultado = traduzir_equivalencias_matriz_para_ppc(matriz_outro, self.ppc)
        self.assertIn("não pertencem ao mesmo curso", resultado["nao_aplicaveis"][0]["motivo"])

        novo_ref2, antigo_ref2 = self.par_matriz("Ambíguo")
        self.vinculo(self.ppc_anterior, antigo_ref2.componente)
        self.vinculo(self.ppc_antigo, antigo_ref2.componente)
        resultado = traduzir_equivalencias_matriz_para_ppc(
            self.matriz, self.ppc, componentes_planejados={novo_ref2.pk},
        )
        self.assertTrue(any("ambiguidade" in item["motivo"] for item in resultado["nao_aplicaveis"]))

    def test_aplicacao_encontra_anterior_no_ancestral_e_sobe_atomicamente(self):
        from django.db import transaction
        from ppc.services.aplicacao_equivalencias import traduzir_equivalencias_matriz_para_ppc
        novo_ref, antigo_ref = self.par_matriz("Ancestral")
        antigo = self.vinculo(self.ppc_antigo, antigo_ref.componente)
        resultado = traduzir_equivalencias_matriz_para_ppc(
            self.matriz, self.ppc, componentes_planejados={novo_ref.pk},
        )
        self.assertEqual(len(resultado["criadas"]), 1)
        novo = self.vinculo(self.ppc, novo_ref.componente)
        original_create = EquivalenciaPPC.objects.create
        chamadas = {"n": 0}
        def falhar_depois_de_criar(*args, **kwargs):
            chamadas["n"] += 1
            criada = original_create(*args, **kwargs)
            if chamadas["n"] == 1:
                raise RuntimeError("falha simulada após inserir o par")
            return criada
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                with patch.object(EquivalenciaPPC.objects, "create", side_effect=falhar_depois_de_criar):
                    traduzir_equivalencias_matriz_para_ppc(self.matriz, self.ppc, usuario=self.user, aplicar=True)
        self.assertFalse(EquivalenciaPPC.objects.filter(item_novo=novo, item_anterior=antigo).exists())


class EquivalenciasEntreEdicoesTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("equiv-user", password="x")
        self.curso = Curso.objects.create(nome="Curso equivalências", unidade_academica="UA", area_conhecimento="Área")
        self.anterior = MatrizReferenciaCurricular.objects.create(curso=self.curso, nome="Edição 1")
        self.nova = MatrizReferenciaCurricular.objects.create(curso=self.curso, nome="Edição 2", matriz_anterior=self.anterior)

    def componente(self, nome, *, ementa="", tipo="disciplina", teoria=64, pratica=0, estudante=0, acex=0):
        return ComponenteCurricular.objects.create(
            nome=nome, ementa=ementa, tipo=tipo, carga_horaria_teorica=teoria,
            carga_horaria_pratica=pratica, carga_horaria_estudante=estudante,
            carga_horaria_acex=acex, unidade_academica_componente="UA",
        )

    def test_sugestao_usa_ementa_normalizada_ch_computada_e_ace_nao_bloqueia(self):
        antigo = ComponenteNaMatrizReferencia.objects.create(
            matriz=self.anterior, componente=self.componente("Antigo", ementa="  Álgebra   linear ", acex=16), periodo=1, natureza="obrigatoria",
        )
        novo = ComponenteNaMatrizReferencia.objects.create(
            matriz=self.nova, componente=self.componente("Novo", ementa="Álgebra linear", teoria=64), periodo=1, natureza="obrigatoria",
        )
        dados = consultar_equivalencias_matriz(self.nova)
        candidato = dados["linhas"][0]["matrizes"][0]["candidatos"][0]
        self.assertEqual(candidato["item"], antigo)
        self.assertTrue(candidato["automatica"])
        self.assertTrue(candidato["selecionada"])
        resumo = salvar_equivalencias_matriz(self.nova.pk, [(novo.pk, antigo.pk)], self.user)
        self.assertEqual(resumo["adicionadas"], 1)
        self.assertTrue(EquivalenciaMatriz.objects.filter(item_novo=novo, item_anterior=antigo).exists())

    def test_matriz_sem_curso_exibe_instrucao_e_nao_falha(self):
        matriz = MatrizReferenciaCurricular.objects.create(nome="Sem curso")
        self.client.force_login(self.user)
        resposta = self.client.get(reverse("equivalencias_matriz", args=[matriz.pk]))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Vincule esta matriz a um curso")

    def test_predecessora_de_outro_curso_e_rejeitada(self):
        outro_curso = Curso.objects.create(nome="Outro curso", unidade_academica="UA", area_conhecimento="Área")
        outra = MatrizReferenciaCurricular.objects.create(curso=outro_curso, nome="Outra")
        matriz = MatrizReferenciaCurricular(curso=self.curso, nome="Inválida", matriz_anterior=outra)
        with self.assertRaises(ValidationError):
            matriz.save()

    def test_sugestao_aplica_apenas_quando_ch_anterior_maior_ou_igual(self):
        antigo = ComponenteNaMatrizReferencia.objects.create(matriz=self.anterior, componente=self.componente("A", ementa="igual", teoria=64), periodo=1, natureza="obrigatoria")
        novo = ComponenteNaMatrizReferencia.objects.create(matriz=self.nova, componente=self.componente("B", ementa="igual", teoria=80), periodo=1, natureza="obrigatoria")
        dados = consultar_equivalencias_matriz(self.nova)
        self.assertEqual(dados["linhas"][0]["matrizes"][0]["candidatos"], [])
        with self.assertRaises(ValidationError):
            salvar_equivalencias_matriz(self.nova.pk, [(novo.pk, antigo.pk)], self.user)

    def test_acex_insuficiente_nao_sugere_previa_e_salvar_rejeita_com_valores(self):
        antigo_comp = self.componente("Anterior ACEx baixo", ementa="Mesma ementa", teoria=80, acex=8)
        novo_comp = self.componente("Novo ACEx alto", ementa="Mesma ementa", teoria=64, acex=16)
        antigo = ComponenteNaMatrizReferencia.objects.create(matriz=self.anterior, componente=antigo_comp, periodo=1, natureza="obrigatoria")
        novo = ComponenteNaMatrizReferencia.objects.create(matriz=self.nova, componente=novo_comp, periodo=1, natureza="obrigatoria")
        self.client.force_login(self.user)

        dados = consultar_equivalencias_matriz(self.nova)
        linha = next(l for l in dados["linhas"] if l["item"].pk == novo.pk)
        self.assertEqual(linha["matrizes"][0]["candidatos"], [])
        endpoint = self.client.get(reverse("candidatos_equivalencia_matriz", args=[self.nova.pk]), {
            "item_id": novo.pk, "matriz_anterior_id": self.anterior.pk,
        }).json()
        candidato = next(c for c in endpoint["candidatos"] if c["id"] == antigo.pk)
        self.assertFalse(candidato["elegivel"])
        self.assertEqual(candidato["acex"], 8)
        self.assertIn("ACEx insuficiente: anterior 8 h, nova 16 h", candidato["motivos_por_condicao"]["acex"])
        antigo_igual = ComponenteNaMatrizReferencia.objects.create(
            matriz=self.anterior, componente=self.componente("Anterior ACEx igual", teoria=64, acex=16),
            periodo=2, natureza="obrigatoria",
        )
        endpoint_atualizado = self.client.get(reverse("candidatos_equivalencia_matriz", args=[self.nova.pk]), {
            "item_id": novo.pk, "matriz_anterior_id": self.anterior.pk,
        }).json()
        self.assertTrue(next(c for c in endpoint_atualizado["candidatos"] if c["id"] == antigo_igual.pk)["elegivel"])

        previa = self.client.post(reverse("previa_equivalencias_matriz", args=[self.nova.pk]),
                                  data=__import__("json").dumps({"pares": [[novo.pk, antigo.pk]]}),
                                  content_type="application/json")
        self.assertIn("ACEx insuficiente: anterior 8 h, nova 16 h", previa.json()["html"])
        salvar = self.client.post(reverse("equivalencias_matriz", args=[self.nova.pk]),
                                  data=__import__("json").dumps({"pares": [[novo.pk, antigo.pk]]}),
                                  content_type="application/json")
        self.assertEqual(salvar.status_code, 400)
        self.assertIn("ACEx insuficiente: anterior 8 h, nova 16 h", salvar.json()["erro"])

        zero = ComponenteNaMatrizReferencia.objects.create(
            matriz=self.nova, componente=self.componente("Novo sem ACEx", ementa="", teoria=64, acex=0),
            periodo=2, natureza="obrigatoria",
        )
        zero_candidatos = self.client.get(reverse("candidatos_equivalencia_matriz", args=[self.nova.pk]), {
            "item_id": zero.pk, "matriz_anterior_id": self.anterior.pk,
        }).json()["candidatos"]
        self.assertTrue(next(c for c in zero_candidatos if c["id"] == antigo.pk)["elegivel"])

        EquivalenciaMatriz.objects.bulk_create([EquivalenciaMatriz(item_novo=novo, item_anterior=antigo)])
        tela = self.client.get(reverse("equivalencias_matriz", args=[self.nova.pk]))
        self.assertEqual(tela.status_code, 200)
        self.assertContains(tela, "1 par(es) fora da regra atual")
        self.assertContains(tela, "ACEx 16 h")
        self.assertContains(tela, "ACEx 8 h")
        self.assertContains(tela, "ACEx insuficiente: anterior 8 h, nova 16 h")
        self.assertTrue(EquivalenciaMatriz.objects.filter(item_novo=novo, item_anterior=antigo).exists())

    def test_conversao_legada_simula_sem_alterar_dados(self):
        grupo = GrupoEquivalenciaComponentes.objects.create()
        antigo = ComponenteNaMatrizReferencia.objects.create(matriz=self.anterior, componente=self.componente("Legado A"), periodo=1, natureza="obrigatoria")
        novo = ComponenteNaMatrizReferencia.objects.create(matriz=self.nova, componente=self.componente("Legado B"), periodo=1, natureza="obrigatoria")
        ItemEquivalencia.objects.create(grupo=grupo, item_matriz=antigo, ordem=1)
        ItemEquivalencia.objects.create(grupo=grupo, item_matriz=novo, ordem=2)
        out = __import__("io").StringIO()
        call_command("converter_equivalencias_legadas", stdout=out)
        self.assertIn("seriam gravados: 1 pares", out.getvalue())
        self.assertEqual(grupo.itens.count(), 2)
        self.assertEqual(EquivalenciaMatriz.objects.count(), 0)

    def test_conversor_separa_motivo_de_acex(self):
        grupo = GrupoEquivalenciaComponentes.objects.create()
        antigo = ComponenteNaMatrizReferencia.objects.create(
            matriz=self.anterior, componente=self.componente("Conversor anterior", teoria=80, acex=8),
            periodo=1, natureza="obrigatoria",
        )
        novo = ComponenteNaMatrizReferencia.objects.create(
            matriz=self.nova, componente=self.componente("Conversor novo", teoria=64, acex=16),
            periodo=1, natureza="obrigatoria",
        )
        ItemEquivalencia.objects.create(grupo=grupo, item_matriz=antigo, ordem=1)
        ItemEquivalencia.objects.create(grupo=grupo, item_matriz=novo, ordem=2)
        out = StringIO()
        call_command("converter_equivalencias_legadas", stdout=out)
        self.assertIn("ACEx: ACEx insuficiente: anterior 8 h, nova 16 h", out.getvalue())
        self.assertEqual(EquivalenciaMatriz.objects.count(), 0)

    def test_html_editor_nao_renderiza_lista_global_de_candidatos_e_usuario_logado_acessa(self):
        antigo = ComponenteNaMatrizReferencia.objects.create(matriz=self.anterior, componente=self.componente("Candidato fora do HTML"), periodo=1, natureza="obrigatoria")
        ComponenteNaMatrizReferencia.objects.create(matriz=self.nova, componente=self.componente("Nova"), periodo=1, natureza="obrigatoria")
        self.client.force_login(self.user)
        resposta = self.client.get(reverse("equivalencias_matriz", args=[self.nova.pk]))
        self.assertEqual(resposta.status_code, 200)
        self.assertNotContains(resposta, "Candidato fora do HTML")
        self.assertContains(resposta, "Selecionar equivalência")
        self.assertContains(resposta, "Verificar Equivalências")

    def test_html_compacto_mostra_apenas_equivalente_selecionado_como_chip(self):
        antigo = ComponenteNaMatrizReferencia.objects.create(matriz=self.anterior, componente=self.componente("Equivalente visível"), periodo=1, natureza="obrigatoria")
        novo = ComponenteNaMatrizReferencia.objects.create(matriz=self.nova, componente=self.componente("Nova visível"), periodo=1, natureza="obrigatoria")
        EquivalenciaMatriz.objects.create(item_novo=novo, item_anterior=antigo, criado_por=self.user)
        self.client.force_login(self.user)
        resposta = self.client.get(reverse("equivalencias_matriz", args=[self.nova.pk]))
        self.assertContains(resposta, "Equivalente visível")
        self.assertContains(resposta, "64 h")
        self.assertContains(resposta, "eq-chip")
        self.assertNotContains(resposta, "ACEx 0 h")

    def test_endpoint_candidatos_somente_matriz_anterior_do_curso_e_desabilita_ch_baixa(self):
        self.componente("Candidato elegível", teoria=64)
        self.componente("Candidato CH baixa", teoria=32)
        estrangeiro = Curso.objects.create(nome="Curso externo", unidade_academica="UA", area_conhecimento="Área")
        matriz_estrangeira = MatrizReferenciaCurricular.objects.create(curso=estrangeiro, nome="Matriz externa")
        c_estrangeiro = ComponenteNaMatrizReferencia.objects.create(matriz=matriz_estrangeira, componente=self.componente("Não deve aparecer"), periodo=1, natureza="obrigatoria")
        comp_nova = self.componente("Componente novo", teoria=64)
        novo = ComponenteNaMatrizReferencia.objects.create(matriz=self.nova, componente=comp_nova, periodo=1, natureza="obrigatoria")
        velho_ok = ComponenteNaMatrizReferencia.objects.create(matriz=self.anterior, componente=ComponenteCurricular.objects.get(nome="Candidato elegível"), periodo=1, natureza="obrigatoria")
        velho_baixo = ComponenteNaMatrizReferencia.objects.create(matriz=self.anterior, componente=ComponenteCurricular.objects.get(nome="Candidato CH baixa"), periodo=1, natureza="obrigatoria")
        self.client.force_login(self.user)
        url = reverse("candidatos_equivalencia_matriz", args=[self.nova.pk])
        response = self.client.get(url, {"item_id": novo.pk, "matriz_anterior_id": self.anterior.pk})
        self.assertEqual(response.status_code, 200)
        itens = {c["id"]: c for c in response.json()["candidatos"]}
        self.assertTrue(itens[velho_ok.pk]["elegivel"])
        self.assertFalse(itens[velho_baixo.pk]["elegivel"])
        self.assertIn("CH total insuficiente", itens[velho_baixo.pk]["motivo"])
        response_forjado = self.client.get(url, {"item_id": novo.pk, "matriz_anterior_id": matriz_estrangeira.pk})
        self.assertEqual(response_forjado.status_code, 400)
        self.assertNotIn(c_estrangeiro.pk, itens)

    def test_previa_revalida_pares_nao_salva_e_lista_rejeitado(self):
        novo_comp = self.componente("Nova CH alta", teoria=80)
        velho_comp = self.componente("Anterior CH baixa", teoria=64)
        novo = ComponenteNaMatrizReferencia.objects.create(matriz=self.nova, componente=novo_comp, periodo=1, natureza="obrigatoria")
        velho = ComponenteNaMatrizReferencia.objects.create(matriz=self.anterior, componente=velho_comp, periodo=1, natureza="obrigatoria")
        self.client.force_login(self.user)
        response = self.client.post(reverse("previa_equivalencias_matriz", args=[self.nova.pk]), data=__import__("json").dumps({"pares": [[novo.pk, velho.pk]]}), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pares rejeitados", html=False)
        self.assertIn("CH total insuficiente", response.json()["html"])
        self.assertFalse(EquivalenciaMatriz.objects.exists())

    def test_salvar_endpoint_rejeita_par_forjado_de_matriz_alheia(self):
        novo = ComponenteNaMatrizReferencia.objects.create(matriz=self.nova, componente=self.componente("Novo save"), periodo=1, natureza="obrigatoria")
        curso_b = Curso.objects.create(nome="B", unidade_academica="UA", area_conhecimento="Área")
        matriz_b = MatrizReferenciaCurricular.objects.create(curso=curso_b, nome="B")
        antigo = ComponenteNaMatrizReferencia.objects.create(matriz=matriz_b, componente=self.componente("Antigo save"), periodo=1, natureza="obrigatoria")
        self.client.force_login(self.user)
        response = self.client.post(reverse("equivalencias_matriz", args=[self.nova.pk]), data=__import__("json").dumps({"pares": [[novo.pk, antigo.pk]]}), content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(EquivalenciaMatriz.objects.exists())


class EquivalenciasPPCInterfaceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("equiv-ppc-user", password="x")
        self.curso = Curso.objects.create(nome="Curso PPC eq", unidade_academica="UA", area_conhecimento="Área")
        base = dict(curso=self.curso, modalidade="presencial", grau_academico="bacharelado", turno_funcionamento="Integral", numero_vagas_anuais=30, duracao_minima_semestres=4, duracao_media_semestres=6, duracao_maxima_semestres=8, diretor="D", vice_diretor="VD", coordenador_curso="C", vice_coordenador_curso="VC", tipo_ppc="novo")
        self.anterior = PPC.objects.create(**base)
        self.novo = PPC.objects.create(**{**base, "tipo_ppc": "reformulacao", "ppc_anterior": self.anterior})
        def comp(nome, ch, ementa=""):
            return ComponenteCurricular.objects.create(nome=nome, codigo=nome[:4], tipo="disciplina", carga_horaria_teorica=ch, carga_horaria_pratica=0, carga_horaria_estudante=0, carga_horaria_acex=0, unidade_academica_componente="UA", ementa=ementa)
        self.antigo = ComponenteNaMatriz.objects.create(ppc=self.anterior, componente=comp("Antigo", 64, "Comum"), periodo=1, natureza="obrigatoria")
        self.atual = ComponenteNaMatriz.objects.create(ppc=self.novo, componente=comp("Atual", 64, "Comum"), periodo=1, natureza="obrigatoria")
        self.client.force_login(self.user)

    def test_editor_ppc_compacto_sem_candidatos_no_html(self):
        response = self.client.get(reverse("equivalencias_ppc", args=[self.novo.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Antigo —")
        self.assertContains(response, "Salvar equivalências")
        self.assertNotContains(response, "ACEx 0 h")

    def test_acex_no_editor_candidato_previa_salvar_e_alerta_legado_ppc(self):
        antigo_comp = ComponenteCurricular.objects.create(
            nome="Anterior com ACEx menor", codigo="AXA", tipo="disciplina",
            carga_horaria_teorica=80, carga_horaria_pratica=0, carga_horaria_acex=8,
            unidade_academica_componente="UA", ementa="Ementa idêntica",
        )
        novo_comp = ComponenteCurricular.objects.create(
            nome="Atual com ACEx maior", codigo="AXB", tipo="disciplina",
            carga_horaria_teorica=64, carga_horaria_pratica=0, carga_horaria_acex=16,
            unidade_academica_componente="UA", ementa="Ementa idêntica",
        )
        antigo = ComponenteNaMatriz.objects.create(ppc=self.anterior, componente=antigo_comp, periodo=2, natureza="obrigatoria")
        novo = ComponenteNaMatriz.objects.create(ppc=self.novo, componente=novo_comp, periodo=2, natureza="obrigatoria")
        url = reverse("candidatos_equivalencia_ppc", args=[self.novo.pk])
        resultado = self.client.get(url, {"item_id": novo.pk, "matriz_anterior_id": self.anterior.pk}).json()
        candidato = next(c for c in resultado["candidatos"] if c["id"] == antigo.pk)
        self.assertFalse(candidato["elegivel"])
        self.assertEqual(candidato["acex"], 8)
        self.assertIn("ACEx insuficiente", candidato["motivos_por_condicao"]["acex"])
        from .services.equivalencias_ppc import preparar_editor_ppc
        self.assertNotIn([novo.pk, self.anterior.pk, antigo.pk], preparar_editor_ppc(self.novo)["automaticas"])
        zero_candidates = self.client.get(url, {
            "item_id": self.atual.pk, "matriz_anterior_id": self.anterior.pk,
        }).json()["candidatos"]
        self.assertTrue(next(c for c in zero_candidates if c["id"] == antigo.pk)["elegivel"])

        previa = self.client.post(reverse("equivalencias_ppc", args=[self.novo.pk]),
                                  data=__import__("json").dumps({"pares": [[novo.pk, antigo.pk]], "preview": True}),
                                  content_type="application/json")
        self.assertIn("ACEx insuficiente: anterior 8 h, nova 16 h", previa.json()["html"])
        salvar = self.client.post(reverse("equivalencias_ppc", args=[self.novo.pk]),
                                  data=__import__("json").dumps({"pares": [[novo.pk, antigo.pk]]}),
                                  content_type="application/json")
        self.assertEqual(salvar.status_code, 400)
        self.assertIn("ACEx insuficiente: anterior 8 h, nova 16 h", salvar.json()["erro"])

        resposta = self.client.get(reverse("equivalencias_ppc", args=[self.novo.pk]))
        self.assertContains(resposta, "ACEx 16 h")
        EquivalenciaPPC.objects.bulk_create([EquivalenciaPPC(item_novo=novo, item_anterior=antigo)])
        legado = self.client.get(reverse("equivalencias_ppc", args=[self.novo.pk]))
        self.assertEqual(legado.status_code, 200)
        self.assertContains(legado, "1 par(es) fora da regra atual")
        self.assertContains(legado, "ACEx 8 h")
        self.assertContains(legado, "ACEx insuficiente: anterior 8 h, nova 16 h")
        self.assertTrue(EquivalenciaPPC.objects.filter(item_novo=novo, item_anterior=antigo).exists())

    def test_candidatos_e_previa_validam_ch_sem_gravar(self):
        baixo_comp = ComponenteCurricular.objects.create(nome="Abaixo", codigo="LOW", tipo="disciplina", carga_horaria_teorica=32, carga_horaria_pratica=0, carga_horaria_estudante=0, carga_horaria_acex=0, unidade_academica_componente="UA", ementa="")
        baixo = ComponenteNaMatriz.objects.create(ppc=self.anterior, componente=baixo_comp, periodo=1, natureza="obrigatoria")
        response = self.client.get(reverse("candidatos_equivalencia_ppc", args=[self.novo.pk]), {"item_id": self.atual.pk, "matriz_anterior_id": self.anterior.pk})
        self.assertEqual(response.status_code, 200)
        candidatos = {i["id"]: i for i in response.json()["candidatos"]}
        self.assertTrue(candidatos[self.antigo.pk]["elegivel"])
        self.assertFalse(candidatos[baixo.pk]["elegivel"])
        self.assertIn("CH total insuficiente", candidatos[baixo.pk]["motivo"])
        preview = self.client.post(reverse("equivalencias_ppc", args=[self.novo.pk]), data=__import__("json").dumps({"pares": [[self.atual.pk, baixo.pk]], "preview": True}), content_type="application/json")
        self.assertEqual(preview.status_code, 200)
        self.assertContains(preview, "Quadro de", html=False)
        self.assertIn("par(es) rejeitado(s)", preview.json()["html"])
        self.assertFalse(EquivalenciaPPC.objects.exists())

    def test_salvar_ppc_registra_par_validado_e_usuario_logado_tem_acesso(self):
        response = self.client.post(reverse("equivalencias_ppc", args=[self.novo.pk]), data=__import__("json").dumps({"pares": [[self.atual.pk, self.antigo.pk]]}), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(EquivalenciaPPC.objects.filter(item_novo=self.atual, item_anterior=self.antigo).exists())

    def test_pdf_renderiza_tabela_de_equivalencias_especifica_do_ppc(self):
        EquivalenciaPPC.objects.create(item_novo=self.atual, item_anterior=self.antigo, criado_por=self.user)
        from django.template.loader import render_to_string
        html = render_to_string("ppc/pdf/ppc_documento.html", {
            "ppc": self.novo,
            "equivalencia_ppcs_anteriores": [self.anterior],
            "equivalencia_linhas": [{"item": self.atual, "celulas": [{"ppc": self.anterior, "itens": [self.antigo]}]}],
        })
        self.assertIn("Quadro de equivalência da estrutura curricular deste PPC", html)
        self.assertIn("Equivalente — Curso PPC eq", html)
        self.assertIn("Antigo", html)

    def test_ppc_anterior_de_outro_curso_nao_e_aceito(self):
        outro = Curso.objects.create(nome="Outro", unidade_academica="UA", area_conhecimento="Área")
        dados = dict(curso=outro, modalidade="presencial", grau_academico="bacharelado", turno_funcionamento="Integral", numero_vagas_anuais=30, duracao_minima_semestres=4, duracao_media_semestres=6, duracao_maxima_semestres=8, diretor="D", vice_diretor="VD", coordenador_curso="C", vice_coordenador_curso="VC", tipo_ppc="novo")
        externo = PPC.objects.create(**dados)
        self.novo.ppc_anterior = externo
        with self.assertRaises(ValidationError): self.novo.save()

class EdicaoVinculoMatrizReferenciaTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("edicao-vinculo", password="x")
        self.staff = User.objects.create_user("edicao-vinculo-staff", password="x", is_staff=True)
        self.curso = Curso.objects.create(nome="Curso vínculo", unidade_academica="UA", area_conhecimento="Área")
        self.matriz = MatrizReferenciaCurricular.objects.create(curso=self.curso, nome="Matriz vínculo", grau_academico="licenciatura", status=MatrizReferenciaCurricular.STATUS_EM_MUDANCA)
        VinculoUsuarioCurso.objects.create(usuario=self.user, curso=self.curso)
        self.componente = ComponenteCurricular.objects.create(
            nome="Catálogo original", codigo="CAT-1", tipo="disciplina", carga_horaria_teorica=64,
            carga_horaria_pratica=0, carga_horaria_estudante=0, carga_horaria_professor=0,
            carga_horaria_acex=0, ementa="Ementa original", unidade_academica_componente="UA",
        )
        self.item = ComponenteNaMatrizReferencia.objects.create(
            matriz=self.matriz, componente=self.componente, periodo=1,
            natureza="obrigatoria", nucleo="NE", grupo_licenciatura=1,
        )
        self.url = reverse("editar_item_matriz_referencia", args=[self.item.pk])

    def post_json(self, dados):
        return self.client.post(self.url, data=__import__("json").dumps(dados), content_type="application/json")

    def test_campos_do_catalogo_sao_ignorados_e_nao_alteram_componente(self):
        self.client.force_login(self.user)
        response = self.post_json({"nome": "Alteração indevida", "ementa": "Ementa alterada", "carga_horaria_teorica": 96, "nucleo": "NC", "natureza": "obrigatoria"})
        self.assertEqual(response.status_code, 200)
        self.componente.refresh_from_db()
        self.assertEqual(self.componente.nome, "Catálogo original")
        self.assertEqual(self.componente.ementa, "Ementa original")
        self.assertEqual(self.componente.carga_horaria_teorica, 64)

    def test_post_somente_vinculo_funciona_e_grupo_apenas_em_licenciatura(self):
        self.client.force_login(self.user)
        response = self.post_json({"natureza": "obrigatoria", "nucleo": "NC", "grupo_licenciatura": 4})
        self.assertEqual(response.status_code, 200)
        self.item.refresh_from_db()
        self.assertEqual(self.item.grupo_licenciatura, 4)
        self.matriz.grau_academico = "bacharelado"
        self.matriz.save()
        response = self.post_json({"natureza": "obrigatoria", "nucleo": "NC", "grupo_licenciatura": 2})
        self.assertEqual(response.status_code, 200)
        self.item.refresh_from_db()
        self.assertIsNone(self.item.grupo_licenciatura)

    def test_pagina_exibe_catalogo_somente_leitura_sem_controles_de_edicao_e_link_staff(self):
        self.client.force_login(self.user)
        resposta = self.client.get(reverse("matriz_referencia_detalhe", args=[self.matriz.pk]))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Dados do catálogo (somente leitura)")
        self.assertContains(resposta, "Ementa original")
        self.assertNotContains(resposta, 'class="campo-nome"')
        self.assertContains(resposta, "Resumo por período")
        self.assertContains(resposta, "Obrig.")
        self.assertNotContains(resposta, "Editar no catálogo")
        self.client.force_login(self.staff)
        staff_response = self.client.get(reverse("matriz_referencia_detalhe", args=[self.matriz.pk]))
        self.assertContains(staff_response, "Editar no catálogo")


class RegrasMatrizRegressaoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.curso = Curso.objects.create(
            nome="Curso de teste", unidade_academica="UA",
            area_conhecimento="Área",
        )
        cls.staff = User.objects.create_user("staff-teste", password="x", is_staff=True)
        cls.user = User.objects.create_user("nde-sem-vinculo", password="x")

    def criar_ppc(self, *, duracoes=(4, 6, 8), status="rascunho"):
        return PPC.objects.create(
            curso=self.curso, modalidade="presencial", grau_academico="bacharelado",
            turno_funcionamento="Integral", numero_vagas_anuais=40,
            duracao_minima_semestres=duracoes[0], duracao_media_semestres=duracoes[1],
            duracao_maxima_semestres=duracoes[2], diretor="D", vice_diretor="VD",
            coordenador_curso="C", vice_coordenador_curso="VC", status=status,
            tipo_ppc="novo",
        )

    def criar_componente(self, nome):
        return ComponenteCurricular.objects.create(
            nome=nome, tipo="disciplina", carga_horaria_teorica=60,
            carga_horaria_pratica=0, unidade_academica_componente="UA", ementa="",
        )

    def criar_bibliografia_referencia(self, item, titulo, autores, tipo="basica", referencia=None):
        return BibliografiaReferencia.objects.create(
            componente_na_matriz_referencia=item, referencia=referencia,
            tipo=tipo, titulo=titulo, autores=autores, editora="Editora",
            cidade="Cidade", ano=2020,
        )

    def criar_bibliografia_ppc(self, item, titulo, autores, tipo="basica", referencia=None):
        return Bibliografia.objects.create(
            componente_na_matriz=item, referencia=referencia,
            tipo=tipo, titulo=titulo, autores=autores, editora="Editora",
            cidade="Cidade", ano=2020,
        )

    def test_diferencas_bibliograficas_identica_adicionar_remover_alterar_e_substituir(self):
        ppc = self.criar_ppc()
        matriz = MatrizReferenciaCurricular.objects.create(curso=self.curso, nome="Referência")
        componente = self.criar_componente("Bibliografia")
        atual = ComponenteNaMatriz.objects.create(ppc=ppc, componente=componente, periodo=1, natureza="obrigatoria")
        fonte = ComponenteNaMatrizReferencia.objects.create(matriz=matriz, componente=componente, periodo=1, natureza="obrigatoria")
        obra_a = ReferenciaBibliografica.objects.create(titulo="Obra A", autores="Autora A", ano=2020)
        obra_b = ReferenciaBibliografica.objects.create(titulo="Obra B", autores="Autora B", ano=2021)

        self.criar_bibliografia_referencia(fonte, "Obra A", "Autora A", referencia=obra_a)
        self.criar_bibliografia_ppc(atual, "Obra A", "Autora A", referencia=obra_a)
        self.assertEqual(calcular_operacoes_bibliografia(fonte, atual), [])

        self.criar_bibliografia_referencia(fonte, "Obra B", "Autora B", referencia=obra_b)
        op = calcular_operacoes_bibliografia(fonte, atual)
        self.assertCountEqual([x["acao"] for x in op], ["adicionar"])

        extra = ReferenciaBibliografica.objects.create(titulo="Extra", autores="Outro", ano=1999)
        self.criar_bibliografia_ppc(atual, "Extra", "Outro", referencia=extra)
        op = calcular_operacoes_bibliografia(fonte, atual)
        self.assertCountEqual([x["acao"] for x in op], ["adicionar", "remover"])

        fonte.bibliografias.all().delete()
        self.criar_bibliografia_referencia(fonte, "Obra A", "Autora A", referencia=obra_a)
        atual.bibliografias.all().delete()
        self.criar_bibliografia_ppc(atual, "Obra A", "Autora A", tipo="complementar", referencia=obra_a)
        op = calcular_operacoes_bibliografia(fonte, atual)
        self.assertEqual([x["acao"] for x in op], ["alterar_tipo"])

        atual.bibliografias.all().delete()
        self.criar_bibliografia_ppc(atual, "obra á", "AUTORA A")
        op = calcular_operacoes_bibliografia(fonte, atual)
        self.assertTrue(any(x["acao"] == "substituir" for x in op))

    def test_bibliografia_manual_identica_e_duplicatas_da_referencia_nao_geram_operacoes_repetidas(self):
        ppc = self.criar_ppc()
        matriz = MatrizReferenciaCurricular.objects.create(curso=self.curso, nome="Referência")
        componente = self.criar_componente("Manual")
        atual = ComponenteNaMatriz.objects.create(ppc=ppc, componente=componente, periodo=1, natureza="obrigatoria")
        fonte = ComponenteNaMatrizReferencia.objects.create(matriz=matriz, componente=componente, periodo=1, natureza="obrigatoria")
        self.criar_bibliografia_referencia(fonte, " Livro  A ", "Autora")
        self.criar_bibliografia_referencia(fonte, "Livro A", "Autora")
        self.criar_bibliografia_ppc(atual, "livro a", "AUTORA")
        self.assertEqual(calcular_operacoes_bibliografia(fonte, atual), [])

    def test_matriz_sem_componentes_e_preview_sem_bibliografias_abrem_sem_confirmacao(self):
        ppc = self.criar_ppc()
        matriz = MatrizReferenciaCurricular.objects.create(curso=self.curso, nome="Vazia")
        self.client.force_login(self.staff)
        resposta = self.client.get(reverse("preview_aplicar_matriz_referencia", args=[ppc.pk, matriz.pk]))
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.context["preview"]["bibliografias_total_operacoes"], 0)
        self.assertContains(resposta, "Aplicar selecionados")

    def test_post_confirma_selecao_parcial_e_ignora_operacao_obsoleta_com_history(self):
        ppc = self.criar_ppc()
        matriz = MatrizReferenciaCurricular.objects.create(curso=self.curso, nome="Referência")
        componente = self.criar_componente("Aplicação")
        ComponenteNaMatriz.objects.create(ppc=ppc, componente=componente, periodo=1, natureza="obrigatoria")
        fonte = ComponenteNaMatrizReferencia.objects.create(matriz=matriz, componente=componente, periodo=1, natureza="obrigatoria")
        ref_a = ReferenciaBibliografica.objects.create(titulo="A", autores="Autora")
        ref_b = ReferenciaBibliografica.objects.create(titulo="B", autores="Autor")
        bib_a = self.criar_bibliografia_referencia(fonte, "A", "Autora", referencia=ref_a)
        self.criar_bibliografia_referencia(fonte, "B", "Autor", referencia=ref_b)
        self.client.force_login(self.staff)
        url = reverse("preview_aplicar_matriz_referencia", args=[ppc.pk, matriz.pk])
        get_response = self.client.get(url)
        self.assertEqual(get_response.status_code, 200)
        op_key = next(
            op["key"]
            for grupo in get_response.context["preview"]["bibliografias_diferencas"]
            for op in grupo["operacoes"]
            if op["fonte"].pk == bib_a.pk
        )
        sem_confirmacao = self.client.post(url, {"bibliografia_operacao": [op_key]})
        self.assertEqual(sem_confirmacao.status_code, 200)
        self.assertEqual(Bibliografia.objects.filter(componente_na_matriz__ppc=ppc).count(), 0)

        aplicacao = self.client.post(url, {
            "confirmar_bibliografias": "on", "bibliografia_operacao": [op_key],
        })
        self.assertEqual(aplicacao.status_code, 200)
        self.assertEqual(Bibliografia.objects.filter(componente_na_matriz__ppc=ppc).count(), 1)
        criada = Bibliografia.objects.get(componente_na_matriz__ppc=ppc)
        self.assertEqual(criada.referencia_id, ref_a.pk)
        self.assertTrue(criada.history.exists())

        # Uma segunda submissão antiga não repete a adição, pois o servidor
        # recalcula o diff depois que a obra já existe no PPC.
        obsoleta = self.client.post(url, {
            "confirmar_bibliografias": "on", "bibliografia_operacao": [op_key],
        })
        self.assertEqual(obsoleta.status_code, 200)
        self.assertEqual(Bibliografia.objects.filter(componente_na_matriz__ppc=ppc).count(), 1)
        self.assertEqual(obsoleta.context["resumo_bibliografias"]["ignoradas"], 1)

    def test_post_executa_remocao_tipo_e_substituicao_com_history(self):
        ppc = self.criar_ppc()
        matriz = MatrizReferenciaCurricular.objects.create(curso=self.curso, nome="Referência")
        componente = self.criar_componente("Operações")
        atual = ComponenteNaMatriz.objects.create(ppc=ppc, componente=componente, periodo=1, natureza="obrigatoria")
        fonte = ComponenteNaMatrizReferencia.objects.create(matriz=matriz, componente=componente, periodo=1, natureza="obrigatoria")
        obra_a = ReferenciaBibliografica.objects.create(titulo="A", autores="Autora")
        obra_b = ReferenciaBibliografica.objects.create(titulo="B", autores="Autor")
        obra_c = ReferenciaBibliografica.objects.create(titulo="C", autores="Outra")
        obra_extra = ReferenciaBibliografica.objects.create(titulo="Extra", autores="Autor")
        self.criar_bibliografia_referencia(fonte, "A", "Autora", "basica", obra_a)
        self.criar_bibliografia_referencia(fonte, "B", "Autor", "basica", obra_b)
        self.criar_bibliografia_referencia(fonte, "C", "Outra", "basica", obra_c)
        antiga_tipo = self.criar_bibliografia_ppc(atual, "A", "Autora", "complementar", obra_a)
        extra = self.criar_bibliografia_ppc(atual, "Extra", "Autor", referencia=obra_extra)
        manual = self.criar_bibliografia_ppc(atual, "C", "Outra")
        self.client.force_login(self.staff)
        url = reverse("preview_aplicar_matriz_referencia", args=[ppc.pk, matriz.pk])
        preview = self.client.get(url)
        operacoes = [op for grupo in preview.context["preview"]["bibliografias_diferencas"] for op in grupo["operacoes"]]
        resposta = self.client.post(url, {
            "confirmar_bibliografias": "on",
            "bibliografia_operacao": [op["key"] for op in operacoes],
        })
        self.assertEqual(resposta.status_code, 200)
        finais = list(atual.bibliografias.order_by("titulo"))
        self.assertEqual(len(finais), 3)
        self.assertEqual({(bib.referencia_id, bib.tipo) for bib in finais}, {
            (obra_a.pk, "basica"), (obra_b.pk, "basica"), (obra_c.pk, "basica"),
        })
        self.assertEqual(resposta.context["resumo_bibliografias"], {
            "adicionadas": 1, "removidas": 1, "alteradas": 1, "substituidas": 1, "ignoradas": 0,
        })
        self.assertGreaterEqual(Bibliografia.history.filter(id__in=[antiga_tipo.pk, extra.pk, manual.pk], history_type="-").count(), 3)

    def test_contagens_do_painel_batem_com_total_dos_detalhes_com_acesso_por_curso(self):
        ppc = self.criar_ppc()
        matriz = MatrizReferenciaCurricular.objects.create(curso=self.curso, nome="Com pendência")
        componente_ppc = self.criar_componente("PPC completo")
        componente_ref = self.criar_componente("Matriz completa")
        item_ppc = ComponenteNaMatriz.objects.create(ppc=ppc, componente=componente_ppc, periodo=1, natureza="obrigatoria")
        item_ref = ComponenteNaMatrizReferencia.objects.create(matriz=matriz, componente=componente_ref, periodo=1, natureza="obrigatoria")
        # 3 + 5 obras distintas evita pendência de mínimo; o registro manual
        # é a única pendência em cada componente.
        for item, ref_model, link_model, attr in (
            (item_ppc, ReferenciaBibliografica, Bibliografia, "componente_na_matriz"),
            (item_ref, ReferenciaBibliografica, BibliografiaReferencia, "componente_na_matriz_referencia"),
        ):
            for tipo, quantidade in (("basica", 3), ("complementar", 5)):
                for i in range(quantidade):
                    obra = ref_model.objects.create(titulo=f"{tipo}-{i}-{attr}", autores="Autoria")
                    link_model.objects.create(
                        **{attr: item}, referencia=obra, tipo=tipo,
                        titulo=obra.titulo, autores=obra.autores,
                    )
            link_model.objects.create(
                **{attr: item}, tipo="basica", titulo="Manual fora", autores="Autoria",
            )

        resumo = resumo_pendencias_bibliograficas()
        self.assertEqual(resumo["componentes_ppc_pendentes"], 1)
        self.assertEqual(resumo["componentes_matriz_pendentes"], 1)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse("painel_institucional")).status_code, 200)
        detalhe_ppc = self.client.get(reverse("detalhe_pendencias_bibliografia_ppc", args=[ppc.pk]))
        detalhe_matriz = self.client.get(reverse("detalhe_pendencias_bibliografia_matriz", args=[matriz.pk]))
        self.assertEqual(detalhe_ppc.context["pagina"].paginator.count, 1)
        self.assertEqual(detalhe_matriz.context["pagina"].paginator.count, 1)
        self.client.force_login(self.user)
        from .models import VinculoUsuarioCurso
        VinculoUsuarioCurso.objects.get_or_create(usuario=self.user, curso=self.curso)
        self.assertEqual(self.client.get(reverse("detalhe_pendencias_bibliografia_ppc", args=[ppc.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("detalhe_pendencias_bibliografia_matriz", args=[matriz.pk])).status_code, 200)

    def test_relacoes_ppc_e_referencia_validam_periodos(self):
        ppc = self.criar_ppc()
        a, b = self.criar_componente("A"), self.criar_componente("B")
        origem = ComponenteNaMatriz.objects.create(ppc=ppc, componente=a, periodo=2, natureza="obrigatoria")
        pre = ComponenteNaMatriz.objects.create(ppc=ppc, componente=b, periodo=1, natureza="obrigatoria")
        RelacaoComponente.objects.create(componente_na_matriz=origem, componente_relacionado_na_matriz=pre, tipo="pre_requisito")
        with self.assertRaises(ValidationError):
            RelacaoComponente(componente_na_matriz=origem, componente_relacionado_na_matriz=origem, tipo="pre_requisito").save()
        posterior = ComponenteNaMatriz.objects.create(ppc=ppc, componente=self.criar_componente("C"), periodo=3, natureza="obrigatoria")
        with self.assertRaises(ValidationError):
            RelacaoComponente(componente_na_matriz=origem, componente_relacionado_na_matriz=posterior, tipo="co_requisito").save()

        matriz = MatrizReferenciaCurricular.objects.create(curso=self.curso, nome="Matriz")
        ro = ComponenteNaMatrizReferencia.objects.create(matriz=matriz, componente=a, periodo=2, natureza="obrigatoria")
        rp = ComponenteNaMatrizReferencia.objects.create(matriz=matriz, componente=b, periodo=1, natureza="obrigatoria")
        RelacaoComponenteReferencia.objects.create(item=ro, item_relacionado=rp, tipo="pre_requisito")
        with self.assertRaises(ValidationError):
            RelacaoComponenteReferencia(item=ro, item_relacionado=ro, tipo="pre_requisito").save()
        rp_posterior = ComponenteNaMatrizReferencia.objects.create(matriz=matriz, componente=self.criar_componente("C"), periodo=3, natureza="obrigatoria")
        with self.assertRaises(ValidationError):
            RelacaoComponenteReferencia(item=ro, item_relacionado=rp_posterior, tipo="co_requisito").save()

    def test_painel_lista_componentes_e_duplicacao_aceitam_legado(self):
        ppc = self.criar_ppc(duracoes=(0, 0, 0))
        ComponenteNaMatriz.objects.create(
            ppc=ppc, componente=self.criar_componente("A"), periodo=1, natureza="obrigatoria"
        )
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse("lista_componentes", args=[ppc.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("painel_institucional")).status_code, 200)
        self.assertEqual(self.client.get(reverse("duplicar_ppc", args=[ppc.pk])).status_code, 200)
        resposta = self.client.post(reverse("duplicar_ppc", args=[ppc.pk]), {"tipo_ppc": "reformulacao"})
        self.assertEqual(resposta.status_code, 302)
        resposta = self.client.post(reverse("duplicar_ppc", args=[ppc.pk]), {
            "tipo_ppc": "reformulacao", "copiar_matriz": "on",
        })
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(PPC.objects.exclude(pk=ppc.pk).count(), 2)

    def test_transicao_status_exige_duracao_e_periodos_suficientes(self):
        ppc = self.criar_ppc(duracoes=(0, 0, 0))
        for status in ("em_revisao", "aprovado"):
            ppc.status = status
            with self.assertRaises(ValidationError):
                ppc.save()
            ppc.refresh_from_db()
        ppc.duracao_minima_semestres = 2
        ppc.duracao_media_semestres = 4
        ppc.duracao_maxima_semestres = 6
        ppc.save()
        ppc.status = "em_revisao"
        with self.assertRaises(ValidationError):
            ppc.save()
        componente = self.criar_componente("A")
        ComponenteNaMatriz.objects.create(ppc=ppc, componente=componente, periodo=2, natureza="obrigatoria")
        ppc.status = "em_revisao"
        ppc.save()
        ppc.status = "aprovado"
        ppc.save()

    def test_copia_preserva_relacao_legada_invalida_e_painel_nao_quebra(self):
        ppc = self.criar_ppc()
        a, b = self.criar_componente("A"), self.criar_componente("B")
        origem = ComponenteNaMatriz.objects.create(ppc=ppc, componente=a, periodo=2, natureza="obrigatoria")
        requisito = ComponenteNaMatriz.objects.create(ppc=ppc, componente=b, periodo=2, natureza="obrigatoria")
        RelacaoComponente.objects.bulk_create([
            RelacaoComponente(componente_na_matriz=origem, componente_relacionado_na_matriz=requisito, tipo="pre_requisito")
        ])
        self.client.force_login(self.staff)
        painel = self.client.get(reverse("painel_institucional"))
        self.assertEqual(painel.status_code, 200)
        self.assertEqual(painel.context["total_relacoes_invalidas"], 1)
        self.client.post(reverse("duplicar_ppc", args=[ppc.pk]), {"copiar_matriz": "on"})
        copias = PPC.objects.exclude(pk=ppc.pk)
        self.assertEqual(copias.count(), 1)
        self.assertEqual(RelacaoComponente.objects.filter(componente_na_matriz__ppc=copias.first()).count(), 1)

    def test_item_legado_acima_do_maximo_pode_editar_natureza_mas_nao_periodo(self):
        ppc = self.criar_ppc(duracoes=(2, 3, 4))
        item = ComponenteNaMatriz(
            ppc=ppc, componente=self.criar_componente("Legado"), periodo=5,
            natureza="obrigatoria",
        )
        item.save(validar_limite_periodo=False)
        item.natureza = "optativa"
        item.save(update_fields=["natureza"])
        item.periodo = 6
        with self.assertRaises(ValidationError):
            item.save(update_fields=["periodo"])

    def test_matriz_referencia_aberta_a_usuario_logado_sem_vinculo_e_template_detalhe(self):
        matriz = MatrizReferenciaCurricular.objects.create(curso=self.curso, nome="Matriz")
        componente = self.criar_componente("A")
        item = ComponenteNaMatrizReferencia.objects.create(matriz=matriz, componente=componente, periodo=1, natureza="obrigatoria")
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("matriz_referencia_detalhe", args=[matriz.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("detalhe_componente_existente_matriz_referencia", args=[matriz.pk, componente.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("buscar_bibliografia_referencia", args=[item.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("relacoes_matriz_referencia", args=[matriz.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("fluxograma_matriz_referencia", args=[matriz.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("exportar_matriz_referencia_xlsx", args=[matriz.pk])).status_code, 200)

    def test_usuario_sem_vinculo_recebe_403_em_tela_de_ppc(self):
        ppc = self.criar_ppc()
        item = ComponenteNaMatriz.objects.create(
            ppc=ppc, componente=self.criar_componente("A"), periodo=1, natureza="obrigatoria"
        )
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("buscar_bibliografia_ppc", args=[item.pk])).status_code, 403)

    def test_vincular_manual_preserva_registro_e_delete_catalogo_libera_set_null(self):
        ppc = self.criar_ppc()
        item = ComponenteNaMatriz.objects.create(
            ppc=ppc, componente=self.criar_componente("A"), periodo=1, natureza="obrigatoria"
        )
        obra = ReferenciaBibliografica.objects.create(titulo="Livro", autores="Autora", ano=2020)
        bib = Bibliografia.objects.create(
            componente_na_matriz=item, tipo="basica", titulo="Livro", autores="Autora", ano=2020,
        )
        self.client.force_login(self.staff)
        resposta = self.client.post(reverse("vincular_bibliografia_ppc", args=[item.pk]), {
            "referencia_id": obra.pk, "tipo": "basica",
        })
        self.assertEqual(resposta.status_code, 302)
        bib.refresh_from_db()
        self.assertEqual(bib.referencia_id, obra.pk)
        bib.titulo = "Título alterado"
        with self.assertRaises(ValidationError):
            bib.save()
        obra.delete()
        bib.refresh_from_db()
        self.assertIsNone(bib.referencia_id)

    def test_exportacao_sem_openpyxl_nao_responde_500(self):
        matriz = MatrizReferenciaCurricular.objects.create(curso=self.curso, nome="Matriz")
        self.client.force_login(self.staff)
        with patch("ppc.views.openpyxl", None):
            resposta = self.client.get(reverse("exportar_matriz_referencia_xlsx", args=[matriz.pk]))
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(resposta.url, reverse("matriz_referencia_detalhe", args=[matriz.pk]))

    def test_importacao_matriz_dry_run_nao_grava_pendencias(self):
        from .services.importacao_matriz_referencia import importar_linhas_normalizadas
        antes = ImportacaoPendencia.objects.count()
        importar_linhas_normalizadas([{
            "confianca": "ambigua", "identificador_origem": "MATRIZ-TESTE", "linha_origem": 1,
        }], dry_run=True)
        self.assertEqual(ImportacaoPendencia.objects.count(), antes)

    def test_reconciliacao_dry_run_nao_vincula_bibliografia(self):
        ppc = self.criar_ppc()
        item = ComponenteNaMatriz.objects.create(
            ppc=ppc, componente=self.criar_componente("A"), periodo=1, natureza="obrigatoria"
        )
        ReferenciaBibliografica.objects.create(titulo="Livro", autores="Autora", ano=2020)
        bib = Bibliografia.objects.create(
            componente_na_matriz=item, tipo="basica", titulo="Livro", autores="Autora", ano=2020,
        )
        call_command("reconciliar_bibliografias", "--dry-run", stdout=StringIO())
        bib.refresh_from_db()
        self.assertIsNone(bib.referencia_id)

    def test_pendencias_na_matriz_mostram_contadores_e_link_para_nde(self):
        matriz = MatrizReferenciaCurricular.objects.create(curso=self.curso, nome="Matriz")
        componente = self.criar_componente("Pendente")
        item = ComponenteNaMatrizReferencia.objects.create(matriz=matriz, componente=componente, periodo=1, natureza="obrigatoria")
        relacionado = ComponenteNaMatrizReferencia.objects.create(matriz=matriz, componente=self.criar_componente("Pré"), periodo=1, natureza="obrigatoria")
        RelacaoComponenteReferencia(item=item, item_relacionado=relacionado, tipo="pre_requisito").save(validar_periodo=False)
        url = reverse("matriz_referencia_detalhe", args=[matriz.pk])
        self.client.force_login(self.user)
        resposta_nde = self.client.get(url)
        self.assertEqual(resposta_nde.status_code, 200)
        self.assertContains(resposta_nde, "Pendências desta matriz")
        self.assertContains(resposta_nde, "Pendência bibliográfica")
        self.assertContains(resposta_nde, "Faltam 3 básicas e 5 complementares")
        self.assertContains(resposta_nde, "1 relação(ões) com período inválido")
        self.assertContains(resposta_nde, reverse("detalhe_pendencias_bibliografia_matriz", args=[matriz.pk]))
        self.assertEqual(self.client.get(reverse("detalhe_pendencias_bibliografia_matriz", args=[matriz.pk])).status_code, 200)
        self.client.force_login(self.staff)
        resposta_staff = self.client.get(url)
        self.assertContains(resposta_staff, reverse("detalhe_pendencias_bibliografia_matriz", args=[matriz.pk]))

    def test_seletor_grupo_aparece_apenas_quando_grau_da_matriz_e_licenciatura(self):
        matriz = MatrizReferenciaCurricular.objects.create(curso=self.curso, nome="Lic", grau_academico="licenciatura")
        bacharel = MatrizReferenciaCurricular.objects.create(curso=self.curso, nome="Bach")
        ComponenteNaMatrizReferencia.objects.create(
            matriz=matriz, componente=self.criar_componente("Com grupo"), periodo=1,
            natureza="obrigatoria", grupo_licenciatura=1,
        )
        from .forms import ComponenteMatrizReferenciaForm
        self.assertIn("grupo_licenciatura", ComponenteMatrizReferenciaForm(matriz=matriz).fields)
        self.assertNotIn("grupo_licenciatura", ComponenteMatrizReferenciaForm(matriz=bacharel).fields)
        self.client.force_login(self.staff)
        self.assertContains(self.client.get(reverse("matriz_referencia_detalhe", args=[matriz.pk])), "Grupo 1")
        self.assertContains(self.client.get(reverse("criar_componente_matriz_referencia", args=[matriz.pk])), "Grupo (licenciatura)")
        self.assertNotContains(self.client.get(reverse("criar_componente_matriz_referencia", args=[bacharel.pk])), "Grupo (licenciatura)")

    def test_save_do_vinculo_zera_grupo_quando_matriz_nao_e_licenciatura(self):
        matriz = MatrizReferenciaCurricular.objects.create(curso=self.curso, nome="Bach", grau_academico="bacharelado")
        item = ComponenteNaMatrizReferencia(
            matriz=matriz, componente=self.criar_componente("Grupo"), periodo=1,
            natureza="obrigatoria", grupo_licenciatura=1,
        )
        item.save()
        item.refresh_from_db()
        self.assertIsNone(item.grupo_licenciatura)

    def test_mudar_grau_pede_confirmacao_e_limpa_grupos_com_historico(self):
        matriz = MatrizReferenciaCurricular.objects.create(curso=self.curso, nome="Lic", grau_academico="licenciatura")
        item = ComponenteNaMatrizReferencia.objects.create(
            matriz=matriz, componente=self.criar_componente("Grupo"), periodo=1,
            natureza="obrigatoria", grupo_licenciatura=2,
        )
        self.client.force_login(self.staff)
        url = reverse("vincular_curso_matriz_referencia", args=[matriz.pk])
        dados = {"nome": matriz.nome, "curso_id": self.curso.pk, "numero_periodos": 8, "grau_academico": "bacharelado"}
        confirmar = self.client.post(url, dados)
        self.assertEqual(confirmar.status_code, 200)
        self.assertContains(confirmar, "limpará 1 grupo")
        matriz.refresh_from_db()
        item.refresh_from_db()
        self.assertEqual(matriz.grau_academico, "licenciatura")
        self.assertEqual(item.grupo_licenciatura, 2)
        self.client.post(url, {**dados, "confirmar_limpeza_grupos": "1"})
        matriz.refresh_from_db()
        item.refresh_from_db()
        self.assertEqual(matriz.grau_academico, "bacharelado")
        self.assertIsNone(item.grupo_licenciatura)
        self.assertTrue(item.history.filter(grupo_licenciatura=2).exists())

    def test_duplicar_matriz_copia_grau_e_grupo(self):
        matriz = MatrizReferenciaCurricular.objects.create(curso=self.curso, nome="Lic", grau_academico="licenciatura")
        item = ComponenteNaMatrizReferencia.objects.create(
            matriz=matriz, componente=self.criar_componente("Grupo"), periodo=1,
            natureza="obrigatoria", grupo_licenciatura=4,
        )
        self.client.force_login(self.staff)
        resposta = self.client.post(reverse("duplicar_matriz_referencia", args=[matriz.pk]))
        copia = MatrizReferenciaCurricular.objects.get(nome="Lic (cópia)")
        item_copiado = ComponenteNaMatrizReferencia.objects.get(matriz=copia, componente=item.componente)
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(copia.grau_academico, "licenciatura")
        self.assertEqual(item_copiado.grupo_licenciatura, 4)

    def test_aplicar_matriz_copia_grupo_e_nucleo_apenas_para_componente_novo(self):
        ppc = self.criar_ppc()
        ppc.grau_academico = "licenciatura"
        ppc.save()
        matriz = MatrizReferenciaCurricular.objects.create(curso=self.curso, nome="Lic", grau_academico="licenciatura")
        novo = self.criar_componente("Novo grupo")
        fonte = ComponenteNaMatrizReferencia.objects.create(
            matriz=matriz, componente=novo, periodo=1, natureza="obrigatoria",
            nucleo="NC", grupo_licenciatura=1,
        )
        existente = self.criar_componente("Existente")
        ComponenteNaMatriz.objects.create(ppc=ppc, componente=existente, periodo=1, natureza="obrigatoria", nucleo="NE", grupo_licenciatura=4)
        ref_existente = ComponenteNaMatrizReferencia.objects.create(
            matriz=matriz, componente=existente, periodo=1, natureza="obrigatoria", nucleo="NC", grupo_licenciatura=1,
        )
        self.client.force_login(self.staff)
        url = reverse("preview_aplicar_matriz_referencia", args=[ppc.pk, matriz.pk])
        preview = self.client.get(url)
        self.assertEqual(preview.context["preview"]["grupos_licenciatura_divergentes"][0]["referencia"].pk, ref_existente.pk)
        self.client.post(url, {f"aplicar_novo_{fonte.pk}": "on"})
        vinculo_novo = ComponenteNaMatriz.objects.get(ppc=ppc, componente=novo)
        self.assertEqual((vinculo_novo.grupo_licenciatura, vinculo_novo.nucleo), (1, "NC"))
        vinculo_existente = ComponenteNaMatriz.objects.get(ppc=ppc, componente=existente)
        self.assertEqual(vinculo_existente.grupo_licenciatura, 4)
        self.assertContains(preview, "grupo diferente da referência")

    def test_preview_avisa_quando_grau_da_matriz_e_do_ppc_divergem(self):
        ppc = self.criar_ppc()
        ppc.grau_academico = "licenciatura"
        ppc.save()
        matriz = MatrizReferenciaCurricular.objects.create(curso=self.curso, nome="Sem grau")
        self.client.force_login(self.staff)
        resposta = self.client.get(reverse("preview_aplicar_matriz_referencia", args=[ppc.pk, matriz.pk]))
        self.assertContains(resposta, "difere do grau da matriz")

    def test_edicao_inline_salva_grupo_no_servidor(self):
        matriz = MatrizReferenciaCurricular.objects.create(curso=self.curso, nome="Lic", grau_academico="licenciatura")
        item = ComponenteNaMatrizReferencia.objects.create(
            matriz=matriz, componente=ComponenteCurricular.objects.create(
                nome="Inline", tipo="disciplina", carga_horaria_teorica=64,
                carga_horaria_pratica=0, ementa="",
            ), periodo=1, natureza="obrigatoria",
        )
        matriz.status = MatrizReferenciaCurricular.STATUS_EM_MUDANCA
        matriz.save()
        self.client.force_login(self.staff)
        resposta = self.client.post(
            reverse("editar_item_matriz_referencia", args=[item.pk]),
            data='{"nome":"Inline","nucleo":"NE","natureza":"obrigatoria","carga_horaria_teorica":"64","carga_horaria_pratica":"0","grupo_licenciatura":"2"}',
            content_type="application/json",
        )
        self.assertEqual(resposta.status_code, 200, resposta.content.decode())
        item.refresh_from_db()
        self.assertEqual(item.grupo_licenciatura, 2)

    def test_carga_semanal_reutiliza_vinculos_ppc_e_matriz_e_exclui_acex(self):
        from .services.carga_semanal import SEMANAS_POR_SEMESTRE, calcular_horas_semanais
        self.assertEqual(SEMANAS_POR_SEMESTRE, 16)
        matriz = MatrizReferenciaCurricular.objects.create(curso=self.curso, nome="Matriz")
        ppc = self.criar_ppc()
        disciplina = ComponenteCurricular.objects.create(nome="8h", tipo="disciplina", carga_horaria_teorica=8, carga_horaria_pratica=0, carga_horaria_acex=8, ementa="")
        atividade = ComponenteCurricular.objects.create(nome="Atividade", tipo="atividade", carga_horaria_teorica=0, carga_horaria_pratica=0, carga_horaria_estudante=16, carga_horaria_professor=8, carga_horaria_acex=16, ementa="")
        ref_itens = [
            ComponenteNaMatrizReferencia.objects.create(matriz=matriz, componente=disciplina, periodo=1, natureza="obrigatoria"),
            ComponenteNaMatrizReferencia.objects.create(matriz=matriz, componente=atividade, periodo=1, natureza="optativa"),
        ]
        ppc_itens = [
            ComponenteNaMatriz.objects.create(ppc=ppc, componente=disciplina, periodo=1, natureza="obrigatoria"),
            ComponenteNaMatriz.objects.create(ppc=ppc, componente=atividade, periodo=1, natureza="optativa"),
        ]
        resultado_ref = calcular_horas_semanais(ref_itens)
        resultado_ppc = calcular_horas_semanais(ppc_itens)
        self.assertEqual(resultado_ref[ref_itens[0].pk]["texto"], "0,5 h/sem")
        self.assertEqual(resultado_ref[ref_itens[1].pk]["texto"], "1 h/sem")
        self.assertEqual(resultado_ref[ref_itens[1].pk]["detalhe"], "Estudante: 1 h/sem")
        self.assertEqual(resultado_ref[ref_itens[0].pk]["total"], resultado_ppc[ppc_itens[0].pk]["total"])

    def test_reconciliador_deixa_duplicata_no_componente_pendente(self):
        ppc = self.criar_ppc()
        item = ComponenteNaMatriz.objects.create(ppc=ppc, componente=self.criar_componente("A"), periodo=1, natureza="obrigatoria")
        obra = ReferenciaBibliografica.objects.create(titulo="Livro", autores="Autora", ano=2020)
        for _ in range(2):
            Bibliografia.objects.create(componente_na_matriz=item, tipo="basica", titulo=obra.titulo, autores=obra.autores, ano=obra.ano)
        saida = StringIO()
        call_command("reconciliar_bibliografias", "--confirmar", stdout=saida)
        self.assertIn("DUPLICATA NO COMPONENTE", saida.getvalue())
        self.assertEqual(item.bibliografias.filter(referencia=obra).count(), 1)
        self.assertEqual(item.bibliografias.filter(referencia__isnull=True).count(), 1)

    def test_vincular_obra_ja_escolhida_em_ppc_ou_matriz_da_mensagem_sem_duplicar(self):
        ppc = self.criar_ppc()
        ppc_item = ComponenteNaMatriz.objects.create(ppc=ppc, componente=self.criar_componente("PPC"), periodo=1, natureza="obrigatoria")
        matriz = MatrizReferenciaCurricular.objects.create(curso=self.curso, nome="Matriz")
        matriz_item = ComponenteNaMatrizReferencia.objects.create(matriz=matriz, componente=self.criar_componente("Matriz"), periodo=1, natureza="obrigatoria")
        obra = ReferenciaBibliografica.objects.create(titulo="Livro", autores="Autora", ano=2020)
        self.criar_bibliografia_ppc(ppc_item, obra.titulo, obra.autores, referencia=obra)
        self.criar_bibliografia_referencia(matriz_item, obra.titulo, obra.autores, referencia=obra)
        self.client.force_login(self.staff)
        respostas = [
            self.client.post(reverse("vincular_bibliografia_ppc", args=[ppc_item.pk]), {"referencia_id": obra.pk, "tipo": "basica"}),
            self.client.post(reverse("vincular_bibliografia_referencia", args=[matriz_item.pk]), {"referencia_id": obra.pk, "tipo": "basica"}),
        ]
        self.assertTrue(all(r.status_code == 302 for r in respostas))
        self.assertEqual(ppc_item.bibliografias.filter(referencia=obra).count(), 1)
        self.assertEqual(matriz_item.bibliografias.filter(referencia=obra).count(), 1)
        from django.contrib.messages import get_messages
        for resposta in respostas:
            self.assertIn("já está vinculada", " ".join(str(m) for m in get_messages(resposta.wsgi_request)))

    def test_excluir_vinculos_nao_apaga_obra_e_permite_vincular_novamente(self):
        ppc = self.criar_ppc()
        ppc_item = ComponenteNaMatriz.objects.create(ppc=ppc, componente=self.criar_componente("PPC"), periodo=1, natureza="obrigatoria")
        matriz = MatrizReferenciaCurricular.objects.create(curso=self.curso, nome="Matriz")
        matriz_item = ComponenteNaMatrizReferencia.objects.create(matriz=matriz, componente=self.criar_componente("Matriz"), periodo=1, natureza="obrigatoria")
        obra = ReferenciaBibliografica.objects.create(titulo="Livro", autores="Autora")
        bib_ppc = self.criar_bibliografia_ppc(ppc_item, obra.titulo, obra.autores, referencia=obra)
        bib_ref = self.criar_bibliografia_referencia(matriz_item, obra.titulo, obra.autores, referencia=obra)
        bib_ppc.delete()
        bib_ref.delete()
        self.assertTrue(ReferenciaBibliografica.objects.filter(pk=obra.pk).exists())
        self.criar_bibliografia_ppc(ppc_item, obra.titulo, obra.autores, referencia=obra)
        self.criar_bibliografia_referencia(matriz_item, obra.titulo, obra.autores, referencia=obra)
        self.assertEqual(ReferenciaBibliografica.objects.filter(pk=obra.pk).count(), 1)


class TemplateURLNameTests(TestCase):
    def _rotas_e_usos(self):
        rotas = {}

        def coletar(patterns, namespace=""):
            for pattern in patterns:
                if isinstance(pattern, URLResolver):
                    prefixo = namespace + (f"{pattern.namespace}:" if pattern.namespace else "")
                    coletar(pattern.url_patterns, prefixo)
                elif isinstance(pattern, URLPattern) and pattern.name:
                    kwarg_names = set(pattern.pattern.converters)
                    if hasattr(pattern.pattern, "regex"):
                        kwarg_names.update(re.findall(r"\(\?P<([^>]+)>", pattern.pattern.regex.pattern))
                    rotas[namespace + pattern.name] = {nome: "1" for nome in kwarg_names}

        coletar(get_resolver().url_patterns)
        return rotas

    def test_todos_os_nomes_literalmente_usados_em_templates_existem(self):
        roots = [Path(__file__).parent / "templates", Path(__file__).parent.parent / "templates"]
        usados = set()
        for root in roots:
            for arquivo in root.rglob("*.html"):
                usados.update(re.findall(r"{%\s*url\s+['\"]([^'\"]+)", arquivo.read_text(encoding="utf-8")))
        self._validar_reverse(usados)

    def test_nomes_literalmente_usados_em_reverse_redirect_e_reverse_lazy(self):
        raiz = Path(__file__).parent
        arquivos = [raiz / "views.py", *raiz.joinpath("services").rglob("*.py")]
        usados = set()
        padrao = re.compile(r"\b(?:reverse|redirect|reverse_lazy)\(\s*['\"]([^'\"]+)['\"]")
        for arquivo in arquivos:
            usados.update(padrao.findall(arquivo.read_text(encoding="utf-8")))
        self._validar_reverse(usados)

    def _validar_reverse(self, usados):
        rotas = self._rotas_e_usos()
        falhas = {}
        for nome in sorted(usados):
            try:
                reverse(nome, kwargs=rotas.get(nome, {}))
            except Exception as exc:
                falhas[nome] = str(exc)
        self.assertFalse(falhas, f"Tags url dos templates que não resolvem: {falhas}")
