"""Testes do contrato de extração e da separação entre revisão e confirmação."""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
import unittest
from unittest.mock import patch
from pathlib import Path


RAIZ_CODIGO = Path(__file__).resolve().parents[2]
if str(RAIZ_CODIGO) not in sys.path:
    sys.path.insert(0, str(RAIZ_CODIGO))

CAMINHO_SCRIPT = Path(__file__).with_name("analisar_pdf_uma_chamada.py")
spec = importlib.util.spec_from_file_location("analisar_pdf_uma_chamada", CAMINHO_SCRIPT)
analise = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = analise
spec.loader.exec_module(analise)


def valor_preenchido(contrato):
    if isinstance(contrato, dict):
        return {chave: valor_preenchido(valor) for chave, valor in contrato.items()}
    if isinstance(contrato, list):
        return []
    if contrato.startswith("inteiro"):
        return 1
    if contrato.startswith("booleano"):
        return True
    if "AAAA-MM-DD" in contrato:
        return "2026-01-01"
    return contrato.split(" | ")[0]


def dados_preenchidos():
    dados = valor_preenchido(analise.CONTRATO_BANCO)
    dados["componentes_curriculares"] = [valor_preenchido(analise.CONTRATO_BANCO["componentes_curriculares"][0])]
    dados["membros_nde"] = [valor_preenchido(analise.CONTRATO_BANCO["membros_nde"][0])]
    return dados


def dados_nulos():
    dados = dados_preenchidos()

    def anular(valor):
        if isinstance(valor, dict):
            return {chave: anular(filho) for chave, filho in valor.items()}
        if isinstance(valor, list):
            return [anular(filho) for filho in valor]
        return None

    dados = anular(dados)
    dados["componentes_curriculares"] = []
    dados["apendices"] = []
    dados["membros_nde"] = []
    dados["ausencias_no_documento"] = []
    dados["proveniencia_campos"] = []
    return dados


class ImportacaoIncompletaTests(unittest.TestCase):
    def pre_save(self, dados):
        return analise.validar_pre_save_django(copy.deepcopy(dados))

    def test_1_json_completamente_preenchido_libera_revisao(self):
        self.assertTrue(self.pre_save(dados_preenchidos())["pronto_para_revisao"])

    def test_2_varios_nulls_ainda_liberam_revisao(self):
        resultado = self.pre_save(dados_nulos())
        self.assertTrue(resultado["pronto_para_revisao"])
        self.assertFalse(resultado["pronto_para_confirmacao"])

    def test_3_nde_somente_com_nomes_libera_revisao(self):
        dados = dados_nulos()
        membro = valor_preenchido(analise.CONTRATO_BANCO["membros_nde"][0])
        membro.update({chave: None for chave in membro if chave != "nome"})
        membro["nome"] = "Prof. X"
        dados["membros_nde"] = [membro]
        self.assertTrue(self.pre_save(dados)["pronto_para_revisao"])

    def test_4_componente_com_cargas_ausentes_libera_revisao(self):
        dados = dados_preenchidos()
        componente = dados["componentes_curriculares"][0]
        componente["carga_horaria_pratica"] = None
        componente["carga_horaria_pcc"] = None
        resultado = self.pre_save(dados)
        self.assertTrue(resultado["pronto_para_revisao"])
        self.assertFalse(resultado["pronto_para_confirmacao"])

    def test_5_campos_obrigatorios_ausentes_bloqueiam_so_confirmacao(self):
        resultado = self.pre_save(dados_nulos())
        self.assertTrue(resultado["pronto_para_revisao"])
        self.assertFalse(resultado["pronto_para_confirmacao"])

    def test_6_json_estruturalmente_invalido_bloqueia_importacao(self):
        dados = dados_preenchidos()
        dados["membros_nde"] = {}
        with self.assertRaisesRegex(ValueError, "deve ser uma lista"):
            self.pre_save(dados)

    def test_7_tipo_incompativel_bloqueia_importacao(self):
        dados = dados_preenchidos()
        dados["ppc"]["carga_horaria_total"] = "duas mil horas"
        with self.assertRaisesRegex(ValueError, "deve ser int"):
            self.pre_save(dados)

    def test_8_curinga_de_auditoria_nao_interfere_com_valores_parciais(self):
        dados = dados_preenchidos()
        dados["componentes_curriculares"].append(copy.deepcopy(dados["componentes_curriculares"][0]))
        dados["componentes_curriculares"][1]["unidade_academica_componente"] = None
        dados["proveniencia_campos"] = [{
            "caminho": "componentes_curriculares[*].unidade_academica_componente",
            "estado": "observacao",
            "evidencia": "metadado que não participa da revisão",
        }]
        self.assertTrue(self.pre_save(dados)["pronto_para_revisao"])

    def test_9_treze_membros_nde_so_com_nome_nao_bloqueiam_revisao(self):
        dados = dados_nulos()
        for indice in range(13):
            membro = valor_preenchido(analise.CONTRATO_BANCO["membros_nde"][0])
            membro.update({chave: None for chave in membro if chave != "nome"})
            membro["nome"] = f"Membro {indice}"
            dados["membros_nde"].append(membro)
        self.assertTrue(self.pre_save(dados)["pronto_para_revisao"])

    def test_10_formularios_validos_liberam_confirmacao(self):
        resultado = self.pre_save(dados_preenchidos())
        self.assertTrue(resultado["pronto_para_revisao"])
        self.assertTrue(resultado["pronto_para_confirmacao"])


class EstrategiaAdaptativaTests(unittest.TestCase):
    def diagnostico(self, *, tokens, paginas, tabelas=0, curriculares=0, repeticao=0):
        return analise.DiagnosticoImportacao(
            tokens_entrada_estimados=tokens, paginas=paginas, tabelas=tabelas,
            ocorrencias_curriculares=curriculares, repeticao_linhas=repeticao,
        )

    def test_pdf_pequeno_medio_e_grande_narrativo_usam_uma_chamada(self):
        for diagnostico in (
            self.diagnostico(tokens=900, paginas=3),
            self.diagnostico(tokens=32_000, paginas=45, tabelas=2),
            # Grande não é sinônimo de complexo: sem listas/tabelas densas,
            # continua na estratégia de uma chamada.
            self.diagnostico(tokens=70_000, paginas=80, tabelas=1, curriculares=4),
        ):
            self.assertEqual(analise.decidir_estrategia(diagnostico).estrategia, "uma_chamada")

    def test_pdf_estruturalmente_complexo_prepara_fallback_sem_perder_tentativa_unica(self):
        decisao = analise.decidir_estrategia(
            self.diagnostico(tokens=60_000, paginas=75, tabelas=25, curriculares=200)
        )
        self.assertEqual(decisao.estrategia, "uma_chamada_com_fallback")

    def test_erro_504_embutido_em_http_200_e_timeout_sem_retry_cego(self):
        erro = analise._resumo_erro_provider({
            "provider": "Nvidia", "choices": [{"finish_reason": "error", "error": {
                "code": 504, "message": "Upstream idle timeout exceeded", "metadata": {}
            }}]
        }, 200)
        self.assertIsNotNone(erro)
        self.assertEqual(erro.categoria, "timeout_provider")
        self.assertFalse(erro.recuperavel)
        self.assertTrue(erro.permite_fallback_particionado)

    def test_504_da_chamada_integral_aciona_fallback_sem_repetir_integral(self):
        texto = "--- PÁGINA 1 ---\n1 Apresentação\nTexto A\n--- PÁGINA 2 ---\n2 Objetivos\nTexto B"
        diagnostico = self.diagnostico(tokens=2_000, paginas=2)
        chamadas = []

        def falso(prompt, caracteres, **kwargs):
            chamadas.append(kwargs["finalidade"])
            if kwargs["finalidade"] == "integral":
                raise analise.ErroOpenRouter("504", categoria="timeout_provider", codigo=504)
            return dados_nulos()

        with patch.object(analise, "analisar_complexidade_pdf", return_value=(texto, diagnostico)):
            dados, saida = analise.analisar_pdf_adaptativo(Path("nao-importa.pdf"), chamador=falso)
        self.assertEqual(chamadas.count("integral"), 1)
        self.assertGreaterEqual(len(chamadas), 2)
        self.assertEqual(saida.estrategia, "fallback_particionado")
        analise.validar_estrutura(dados)

    def test_autenticacao_nao_aciona_particionamento(self):
        texto = "--- PÁGINA 1 ---\n1 Apresentação\nTexto A\n--- PÁGINA 2 ---\n2 Objetivos\nTexto B"
        diagnostico = self.diagnostico(tokens=2_000, paginas=2)
        chamadas = []

        def falso(prompt, caracteres, **kwargs):
            chamadas.append(kwargs["finalidade"])
            raise analise.ErroOpenRouter("não autorizado", categoria="autenticacao", codigo=401)

        with patch.object(analise, "analisar_complexidade_pdf", return_value=(texto, diagnostico)):
            with self.assertRaisesRegex(analise.ErroOpenRouter, "não autorizado"):
                analise.analisar_pdf_adaptativo(Path("nao-importa.pdf"), chamador=falso)
        self.assertEqual(chamadas, ["integral"])

    def test_jsons_reais_existentes_preservam_o_contrato(self):
        resultados = Path(__file__).with_name("resultados")
        arquivos = [arquivo for arquivo in resultados.glob("*.json") if not arquivo.name.endswith(".pre_save.json")]
        self.assertGreaterEqual(len(arquivos), 4)
        for arquivo in arquivos:
            with self.subTest(arquivo=arquivo.name):
                dados = json.loads(arquivo.read_text(encoding="utf-8"))
                analise.validar_estrutura(dados)


if __name__ == "__main__":
    unittest.main()
