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
    ImportacaoPendencia,
)
from .services.comparacao_bibliografias import calcular_operacoes_bibliografia
from .services.painel_bibliografias import resumo_pendencias_bibliograficas


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
