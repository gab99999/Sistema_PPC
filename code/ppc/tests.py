import re
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse, get_resolver, URLPattern, URLResolver
from django.core.management import call_command

from .models import (
    Curso, PPC, ComponenteCurricular, ComponenteNaMatriz,
    RelacaoComponente, MatrizReferenciaCurricular,
    ComponenteNaMatrizReferencia, RelacaoComponenteReferencia,
    ReferenciaBibliografica, Bibliografia, BibliografiaReferencia,
    ImportacaoPendencia, EquivalenciaMatriz, GrupoEquivalenciaComponentes, ItemEquivalencia,
)
from .services.comparacao_bibliografias import calcular_operacoes_bibliografia
from .services.painel_bibliografias import resumo_pendencias_bibliograficas
from .services.equivalencias_matrizes import consultar_equivalencias_matriz, salvar_equivalencias_matriz


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
        self.assertNotContains(resposta, "Equivalente visível")
        self.assertContains(resposta, "1 · 64 h")
        self.assertContains(resposta, "eq-chip")

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
        self.assertIn("menor", itens[velho_baixo.pk]["motivo"])
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
        self.assertIn("menor que a CH nova", response.json()["html"])
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


class EdicaoVinculoMatrizReferenciaTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("edicao-vinculo", password="x")
        self.staff = User.objects.create_user("edicao-vinculo-staff", password="x", is_staff=True)
        self.curso = Curso.objects.create(nome="Curso vínculo", unidade_academica="UA", area_conhecimento="Área")
        self.matriz = MatrizReferenciaCurricular.objects.create(curso=self.curso, nome="Matriz vínculo", grau_academico="licenciatura")
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

    def test_contagens_do_painel_batem_com_total_dos_detalhes_e_paginas_exigem_staff(self):
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
        self.assertEqual(self.client.get(reverse("detalhe_pendencias_bibliografia_ppc", args=[ppc.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("detalhe_pendencias_bibliografia_matriz", args=[matriz.pk])).status_code, 403)

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

    def test_pendencias_na_matriz_mostram_contadores_e_link_somente_staff(self):
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
        self.assertNotContains(resposta_nde, reverse("detalhe_pendencias_bibliografia_matriz", args=[matriz.pk]))
        self.assertEqual(self.client.get(reverse("detalhe_pendencias_bibliografia_matriz", args=[matriz.pk])).status_code, 403)
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
        self.client.force_login(self.user)
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
        self.client.force_login(self.user)
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
