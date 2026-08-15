"""Protótipo de análise integral de um PPC em UMA chamada de API.

Configuração (no arquivo ``code/.env``, nunca neste código):

    OPENROUTER_API_KEY=sua_chave
    OPENROUTER_API_URL=https://openrouter.ai/api/v1/chat/completions

Exemplo:

    python ppc/testes/analisar_pdf_uma_chamada.py \
        "ppc/testes/Cópia de Proposta de PPC - Matemática.pdf"

O modelo é intencionalmente fixado em ``nvidia/nemotron-3.5-lightning:free``.
O PDF inteiro é enviado em uma única chamada por tentativa; não há chunking.
Os ~203 mil caracteres do PDF de teste representam aproximadamente 51 mil tokens
(estimativa conservadora de 4 caracteres/token), abaixo do contexto de 1M. O
contrato e a resposta ocupam contexto adicional, mas não justificam dividir o PDF.

O resultado é salvo ao lado deste script em ``resultados/``. Nenhum registro é
gravado no MySQL: os ModelForms existentes são validados em memória para gerar
um pré-save que deve ser revisado e confirmado posteriormente pela interface.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pdfplumber


RAIZ_CODIGO = Path(__file__).resolve().parents[2]
if str(RAIZ_CODIGO) not in sys.path:
    sys.path.insert(0, str(RAIZ_CODIGO))

MODELO_OPENROUTER = "nvidia/nemotron-3.5-lightning:free"
URL_OPENROUTER_PADRAO = "https://openrouter.ai/api/v1/chat/completions"
TIMEOUT_SEGUNDOS = 300
BACKOFF_SEGUNDOS = (2, 4, 8)


def carregar_configuracao_local() -> None:
    """Lê apenas variáveis ausentes do .env, sem depender de pacote extra."""
    caminho_env = RAIZ_CODIGO / ".env"
    if not caminho_env.is_file():
        return
    for linha in caminho_env.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        chave, valor = chave.strip(), valor.strip().strip('"').strip("'")
        if (chave.startswith("LLM_") or chave.startswith("OPENROUTER_")) and chave not in os.environ:
            os.environ[chave] = valor


carregar_configuracao_local()


# As chaves são nomes de campos do banco. As relações usam nomes durante a
# extração; na etapa de importação Django eles serão resolvidos para IDs.
CONTRATO_BANCO = {
    "curso": {
        "nome": "string ou null",
        "unidade_academica": "string ou null",
        "area_conhecimento": "string ou null",
    },
    "ppc": {
        "modalidade": "presencial | ead | null",
        "grau_academico": "bacharelado | licenciatura | null",
        "turno_funcionamento": "string ou null",
        "carga_horaria_total": "inteiro ou null",
        "numero_vagas_anuais": "inteiro ou null",
        "duracao_minima_semestres": "inteiro ou null",
        "duracao_media_semestres": "inteiro ou null",
        "duracao_maxima_semestres": "inteiro ou null",
        "diretor": "string ou null",
        "vice_diretor": "string ou null",
        "coordenador_curso": "string ou null",
        "numero_resolucao": "string ou null",
        "tipo_ppc": "novo | reformulacao | null",
        "publico_alvo_ead": "string ou null",
        "ato_integracao_uab": "string ou null",
        "ato_credenciamento_mec": "string ou null",
        "polos_ead": "string ou null",
        "apresentacao_texto": "string ou null",
        "exposicao_motivos": "string ou null",
        "objetivo_geral": "string ou null",
        "objetivo_especifico": "string ou null",
        "principios_geral": "string ou null",
        "principios_pratica_profissional": "string ou null",
        "principios_formacao_tecnica": "string ou null",
        "principios_formacao_etica_social": "string ou null",
        "principios_interdisciplinaridade": "string ou null",
        "principios_articulacao_teoria_pratica": "string ou null",
        "perfil_curso": "string ou null",
        "perfil_habilidades": "string ou null",
        "estrutura_curricular_descricao": "string ou null",
        "estrutura_curricular_informacoes_complementares": "string ou null",
        "estagio": "string ou null",
        "tcc": "string ou null",
        "atividades_complementares": "string ou null",
        "politicas_integrada": "string ou null",
        "avaliacao_ensino_aprendizagem": "string ou null",
        "avaliacao_projeto_curso": "string ou null",
        "qualificacao": "string ou null",
        "diretrizes_curriculares_nacionais_curso": "string ou null",
        "diretrizes_curriculares_nacionais_educacao_basica": "string ou null",
        "diretrizes_etnico_raciais_historia_cultura_afro_indigena": "string ou null",
        "diretrizes_educacao_direitos_humanos": "string ou null",
        "protecao_direitos_pessoa_transtorno_espectro_autista": "string ou null",
        "componente_curricular_libras": "string ou null",
        "politicas_educacao_ambiental": "string ou null",
        "diretrizes_formacao_professores_educacao_basica": "string ou null",
        "condicoes_acesso_pessoas_deficiencia_mobilidade_reduzida": "string ou null",
        "bibliografias_ppc": "string ou null",
    },
    "dinamica_ead": {
        "dinamica_atividades_presenciais_distancia": "string ou null",
        "recuperacao_estudos_permanencia": "string ou null",
        "componente_informatica_basica": "string ou null",
        "atuacao_tutoria": "string ou null",
        "atribuicoes_profissionais": "string ou null",
        "material_didatico": "string ou null",
        "ferramentas_comunicacao": "string ou null",
        "carga_horaria_presencial_acompanhamento": "string ou null",
        "armazenamento_gerenciamento_dados": "string ou null",
    },
    "componentes_curriculares": [
        {
            "nome": "string",
            "tipo": "disciplina | modulo | seminario | atividade",
            "natureza": "obrigatoria | optativa",
            "nucleo": "NC | NE | NL | AC | ACEx",
            "periodo": "inteiro",
            "carga_horaria_teorica": "inteiro",
            "carga_horaria_pratica": "inteiro",
            "carga_horaria_pcc": "inteiro",
            "unidade_academica_componente": "string",
            "ementa": "string",
            "bibliografias": [
                {
                    "tipo": "basica | complementar",
                    "titulo": "string",
                    "autores": "string",
                    "editora": "string ou null",
                    "cidade": "string ou null",
                    "ano": "inteiro ou null",
                }
            ],
            "relacoes": [
                {
                    "tipo": "pre_requisito | co_requisito | equivalente",
                    "componente_relacionado_nome": "string",
                }
            ],
        }
    ],
    "apendices": [
        {"tipo": "corpo_docente | quadro_oferta", "titulo": "string", "descricao": "string ou null"}
    ],
    "membros_nde": [
        {
            "nome": "string",
            "titulacao": "doutor | mestre | especialista | graduado",
            "regime_trabalho": "de | 40h | 20h",
            "funcao": "presidente | membro",
            "portaria_designacao": "string ou null",
            "data_inicio": "AAAA-MM-DD ou null",
            "data_fim": "AAAA-MM-DD ou null",
            "ativo": "booleano",
        }
    ],
    "ausencias_no_documento": [
        {
            "caminho": "metadado legado opcional",
            "motivo": "metadado legado opcional",
        }
    ],
    "proveniencia_campos": [
        {
            "caminho": "metadado opcional de auditoria",
            "estado": "texto livre",
            "evidencia": "texto livre",
        }
    ],
}


def extrair_texto_integral(caminho: Path) -> str:
    """Lê todas as páginas antes da única chamada remota."""
    with pdfplumber.open(caminho) as pdf:
        paginas = [pagina.extract_text() or "" for pagina in pdf.pages]
    texto = "\n\n".join(f"--- PÁGINA {numero} ---\n{pagina}" for numero, pagina in enumerate(paginas, 1))
    if not texto.strip():
        raise ValueError("O PDF não possui texto extraível; será necessário OCR antes da análise.")
    return texto


def montar_prompt(texto_pdf: str) -> str:
    contrato = json.dumps(CONTRATO_BANCO, ensure_ascii=False, indent=2)
    return f"""Você extrai dados de um Projeto Pedagógico de Curso brasileiro.
Analise TODO o documento a seguir e devolva EXCLUSIVAMENTE um objeto JSON válido.

Regras obrigatórias:
1. Extraia somente informações claramente presentes; não invente, não estime e não calcule
   valores ausentes. Preserve os textos narrativos encontrados.
2. Use somente as chaves do contrato. Para uma informação não encontrada, use null; para
   uma lista não encontrada, use []. Isso é uma extração válida: o usuário completará os
   campos na etapa de revisão.
3. Respeite os tipos e valores enumerados do contrato. Componentes curriculares, bibliografias,
   relações e membros do NDE devem ser listas de objetos quando existirem.
4. Em tabelas quantitativas, devolva 0 somente quando a tabela demonstrar explicitamente zero.
   Não converta '-' globalmente e nunca calcule duração média a partir de mínimo/máximo.
5. Não precisa provar que um campo está ausente do documento nem produzir classificação de
   proveniência. Devolva `ausencias_no_documento` e `proveniencia_campos` como listas vazias.
6. O campo 'curso' descreve o PDF, mas a futura tela Django decidirá se cria ou reutiliza
   o Curso existente.

CONTRATO JSON:
{contrato}

DOCUMENTO COMPLETO:
{texto_pdf}"""


class ErroOpenRouter(RuntimeError):
    """Erro preservando se uma tentativa pode ser repetida com segurança."""

    def __init__(self, mensagem: str, recuperavel: bool = False):
        super().__init__(mensagem)
        self.recuperavel = recuperavel


def _texto_sem_fence(conteudo: str) -> str:
    conteudo = conteudo.strip()
    if conteudo.startswith("```"):
        linhas = conteudo.splitlines()
        if linhas and linhas[0].strip().lower() in {"```", "```json"}:
            linhas = linhas[1:]
        if linhas and linhas[-1].strip() == "```":
            linhas = linhas[:-1]
        conteudo = "\n".join(linhas).strip()
    return conteudo


def _resumo_erro_provider(payload: dict[str, Any], status_http: int | None) -> ErroOpenRouter | None:
    """Distingue uma resposta 200 com erro do provider de um JSON do modelo."""
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ErroOpenRouter(
            f"OpenRouter retornou HTTP {status_http or 'desconhecido'}, mas sem choices na resposta.",
            recuperavel=status_http is not None and status_http >= 500,
        )
    escolha = choices[0]
    if not isinstance(escolha, dict):
        return ErroOpenRouter("OpenRouter retornou choices[0] em formato inválido.")

    erro = escolha.get("error")
    if not isinstance(erro, dict):
        return None

    metadata = erro.get("metadata") if isinstance(erro.get("metadata"), dict) else {}
    codigo = erro.get("code", "desconhecido")
    mensagem = erro.get("message", "sem mensagem")
    tipo = metadata.get("error_type", "desconhecido")
    modelo = payload.get("model", MODELO_OPENROUTER)
    provider = payload.get("provider", "desconhecido")
    finish = escolha.get("finish_reason")
    native_finish = escolha.get("native_finish_reason")
    print(
        "Resposta com erro do provider: "
        f"HTTP status={status_http}; model={modelo}; provider={provider}; "
        f"finish_reason={finish}; native_finish_reason={native_finish}; "
        f"error.code={codigo}; error.message={mensagem}; error_type={tipo}."
    )
    recuperavel = codigo == 502 and tipo == "provider_unavailable"
    texto = (
        f"OpenRouter recebeu a requisição, mas o provider {provider} retornou erro "
        f"{codigo} ({tipo}): {mensagem}. "
        f"HTTP status da API: {status_http or 'não informado'}; modelo: {modelo}; "
        f"finish_reason: {finish}; native_finish_reason: {native_finish}."
    )
    return ErroOpenRouter(texto, recuperavel=recuperavel)


def _interpretar_resposta(payload: Any, status_http: int | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ErroOpenRouter(f"OpenRouter retornou HTTP {status_http or 'desconhecido'} com JSON que não é objeto.")
    erro_provider = _resumo_erro_provider(payload, status_http)
    if erro_provider:
        raise erro_provider

    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ErroOpenRouter("OpenRouter não retornou choices na resposta de sucesso.")
    escolha = choices[0]
    if not isinstance(escolha, dict):
        raise ErroOpenRouter("OpenRouter retornou choices[0] em formato inválido.")
    mensagem = escolha.get("message")
    if not isinstance(mensagem, dict):
        raise ErroOpenRouter("OpenRouter não retornou message em choices[0].")
    conteudo = mensagem.get("content")
    if not isinstance(conteudo, str) or not conteudo.strip():
        raise ErroOpenRouter(
            "OpenRouter retornou resposta sem content final. "
            f"HTTP status: {status_http or 'não informado'}; model: {payload.get('model', MODELO_OPENROUTER)}; "
            f"provider: {payload.get('provider', 'desconhecido')}; "
            f"finish_reason: {escolha.get('finish_reason')}; "
            f"native_finish_reason: {escolha.get('native_finish_reason')}."
        )

    try:
        dados = json.loads(_texto_sem_fence(conteudo))
    except json.JSONDecodeError as erro:
        raise ErroOpenRouter(
            "O provider entregou content, mas ele não contém JSON válido: "
            f"{erro.msg} (linha {erro.lineno}, coluna {erro.colno})."
        ) from erro
    if not isinstance(dados, dict):
        raise ErroOpenRouter("O content do provider contém JSON válido, mas o resultado não é um objeto JSON.")
    return dados


def chamar_api(prompt: str, caracteres_documento: int) -> dict[str, Any]:
    url = os.getenv("OPENROUTER_API_URL") or os.getenv("LLM_API_URL") or URL_OPENROUTER_PADRAO
    chave = os.getenv("OPENROUTER_API_KEY") or os.getenv("LLM_API_KEY")
    if not chave:
        raise RuntimeError("Defina OPENROUTER_API_KEY em code/.env.")

    corpo = {
        "model": MODELO_OPENROUTER,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": "Responda somente JSON válido."},
            {"role": "user", "content": prompt},
        ],
    }
    print(
        f"Configuração da chamada: model={MODELO_OPENROUTER}; "
        f"caracteres do PDF={caracteres_documento:,}; URL={url}; "
        f"API key configurada={bool(chave)}."
    )
    for tentativa in range(1, 4):
        print(f"Tentativa {tentativa}/3 para OpenRouter...")
        requisicao = urllib.request.Request(
            url,
            data=json.dumps(corpo, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": f"Bearer {chave}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(requisicao, timeout=TIMEOUT_SEGUNDOS) as resposta:
                return _interpretar_resposta(json.load(resposta), resposta.status)
        except urllib.error.HTTPError as erro:
            detalhe = erro.read().decode("utf-8", errors="replace")
            recuperavel = erro.code >= 500 or erro.code == 429
            excecao = ErroOpenRouter(f"OpenRouter respondeu HTTP {erro.code}: {detalhe}", recuperavel)
        except ErroOpenRouter as erro:
            excecao = erro
        except (urllib.error.URLError, TimeoutError) as erro:
            excecao = ErroOpenRouter(f"Falha de rede ao chamar OpenRouter: {erro}", recuperavel=True)

        if not excecao.recuperavel or tentativa == 3:
            raise excecao
        espera = BACKOFF_SEGUNDOS[tentativa - 1]
        print(f"Erro recuperável: {excecao}. Nova tentativa em {espera}s.")
        time.sleep(espera)
    raise AssertionError("Fluxo de tentativas inesperado.")


def _tipo_esperado(descricao: str) -> type:
    if descricao.startswith("inteiro"):
        return int
    if descricao.startswith("booleano"):
        return bool
    return str


def _validar_valor_estrutural(valor: Any, contrato: Any, caminho: str) -> None:
    """Valida forma e tipos; ``null`` é sempre uma extração incompleta aceitável."""
    if isinstance(contrato, dict):
        if not isinstance(valor, dict):
            raise ValueError(f"'{caminho}' deve ser um objeto JSON.")
        if set(valor) != set(contrato):
            raise ValueError(
                f"Chaves incorretas em '{caminho}'. Esperadas: {sorted(contrato)}; "
                f"recebidas: {sorted(valor)}"
            )
        for chave, filho_contrato in contrato.items():
            _validar_valor_estrutural(valor[chave], filho_contrato, f"{caminho}.{chave}")
        return
    if isinstance(contrato, list):
        if not isinstance(valor, list):
            raise ValueError(f"'{caminho}' deve ser uma lista.")
        for indice, item in enumerate(valor):
            _validar_valor_estrutural(item, contrato[0], f"{caminho}[{indice}]")
        return
    if valor is None:
        return
    tipo = _tipo_esperado(contrato)
    if type(valor) is not tipo:
        raise ValueError(f"'{caminho}' deve ser {tipo.__name__} ou null, não {type(valor).__name__}.")


def validar_estrutura(dados: dict[str, Any]) -> None:
    """Bloqueia somente JSON corrompido ou incompatível com o contrato de extração."""
    if not isinstance(dados, dict):
        raise ValueError("A resposta da IA deve ser um objeto JSON.")
    # Metadados de proveniência são opcionais e nunca influenciam a revisão.
    dados.setdefault("ausencias_no_documento", [])
    dados.setdefault("proveniencia_campos", [])
    if set(dados) != set(CONTRATO_BANCO):
        raise ValueError(f"Chaves incorretas. Esperadas: {sorted(CONTRATO_BANCO)}; recebidas: {sorted(dados)}")
    for chave, contrato in CONTRATO_BANCO.items():
        _validar_valor_estrutural(dados[chave], contrato, chave)


def _dados_formulario(dados: dict[str, Any], campos: list[str]) -> dict[str, Any]:
    """ModelForms recebem string vazia para ausências, não o literal JSON null."""
    return {campo: "" if dados.get(campo) is None else dados.get(campo, "") for campo in campos}


def _erros_formulario(formulario: Any) -> dict[str, Any]:
    return formulario.errors.get_json_data(escape_html=False)


def _resultado_formulario(formulario: Any, dados_enviados: dict[str, Any]) -> dict[str, Any]:
    """Registra o resultado do ModelForm e o valor que originou cada erro.

    O relatório de pré-save precisa distinguir uma ausência na extração de um
    problema de mapeamento/validação, sem alterar nem persistir a instância.
    """
    valido = formulario.is_valid()
    erros = _erros_formulario(formulario)
    return {
        "valido": valido,
        "erros": erros,
        "valores_enviados_com_erro": {
            campo: dados_enviados.get(campo)
            for campo in erros
            if campo in dados_enviados
        },
    }


def validar_pre_save_django(dados: dict[str, Any]) -> dict[str, Any]:
    """Executa os ModelForms do CRUD sem gravar curso, PPC ou entidades filhas.

    O CRUD atual cria o Curso antes do PPC e usa ModelForms separados por tela.
    Esta rotina replica essas validações em memória. Relações entre componentes
    ficam pendentes porque ainda não existem IDs de componentes confirmados.
    """
    validar_estrutura(dados)
    if str(RAIZ_CODIGO) not in sys.path:
        sys.path.insert(0, str(RAIZ_CODIGO))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()
    from ppc.forms import (
        ApresentacaoForm, ApendiceForm, AtividadesComplementaresForm,
        AvaliacaoEnsinoForm, AvalicaoProjetoCursoForm, BibliografiaForm,
        ComponenteCurricularForm, CursoForm, DinamicaEADForm, EstagioForm,
        ExpectativasForm, ExposicaoMotivosForm, InformacoesGeraisForm,
        MembroNDEForm, ObjetivosForm, PoliticasIntegradaForm, PrincipiosForm,
        QualificacaoForm, ReferenciasForm, RequisitosLegaisForm,
        EstruturaCurricularForm, TccForm,
    )

    definicoes_ppc = [
        ("informacoes_gerais", InformacoesGeraisForm, [
            "modalidade", "grau_academico", "turno_funcionamento", "carga_horaria_total",
            "numero_vagas_anuais", "duracao_minima_semestres", "duracao_media_semestres",
            "duracao_maxima_semestres", "diretor", "vice_diretor", "coordenador_curso",
            "tipo_ppc", "status", "numero_resolucao",
        ]),
        ("apresentacao", ApresentacaoForm, ["apresentacao_texto", "publico_alvo_ead", "ato_integracao_uab", "ato_credenciamento_mec", "polos_ead"]),
        ("exposicao_motivos", ExposicaoMotivosForm, ["tipo_ppc", "exposicao_motivos"]),
        ("objetivos", ObjetivosForm, ["objetivo_geral", "objetivo_especifico"]),
        ("principios", PrincipiosForm, ["principios_geral", "principios_pratica_profissional", "principios_formacao_tecnica", "principios_formacao_etica_social", "principios_interdisciplinaridade", "principios_articulacao_teoria_pratica"]),
        ("expectativas", ExpectativasForm, ["perfil_curso", "perfil_habilidades"]),
        ("estrutura_curricular", EstruturaCurricularForm, ["estrutura_curricular_descricao", "estrutura_curricular_informacoes_complementares"]),
        ("estagio", EstagioForm, ["estagio"]), ("tcc", TccForm, ["tcc"]),
        ("atividades_complementares", AtividadesComplementaresForm, ["atividades_complementares"]),
        ("politicas_integrada", PoliticasIntegradaForm, ["politicas_integrada"]),
        ("avaliacao_ensino", AvaliacaoEnsinoForm, ["avaliacao_ensino_aprendizagem"]),
        ("avaliacao_projeto", AvalicaoProjetoCursoForm, ["avaliacao_projeto_curso"]),
        ("qualificacao", QualificacaoForm, ["qualificacao"]),
        ("requisitos_legais", RequisitosLegaisForm, [
            "diretrizes_curriculares_nacionais_curso", "diretrizes_curriculares_nacionais_educacao_basica",
            "diretrizes_etnico_raciais_historia_cultura_afro_indigena", "diretrizes_educacao_direitos_humanos",
            "protecao_direitos_pessoa_transtorno_espectro_autista", "componente_curricular_libras",
            "politicas_educacao_ambiental", "diretrizes_formacao_professores_educacao_basica",
            "condicoes_acesso_pessoas_deficiencia_mobilidade_reduzida",
        ]), ("referencias", ReferenciasForm, ["bibliografias_ppc"]),
    ]
    dados_ppc = dict(dados["ppc"])
    dados_ppc["status"] = "rascunho"
    formularios: dict[str, Any] = {}
    dados_curso = _dados_formulario(dados["curso"], ["nome", "unidade_academica", "area_conhecimento"])
    curso_form = CursoForm(dados_curso)
    for nome, classe, campos in definicoes_ppc:
        formularios[nome] = (classe, _dados_formulario(dados_ppc, campos))

    resultados = {"curso": _resultado_formulario(curso_form, dados_curso)}
    for nome, (classe, dados_formulario) in formularios.items():
        resultados[nome] = _resultado_formulario(classe(dados_formulario), dados_formulario)
    componentes = []
    for indice, componente in enumerate(dados["componentes_curriculares"]):
        dados_componente = _dados_formulario(componente, list(ComponenteCurricularForm.Meta.fields))
        form = ComponenteCurricularForm(dados_componente)
        item = {"indice": indice, "nome": componente.get("nome"), **_resultado_formulario(form, dados_componente), "bibliografias": []}
        for bib_indice, bibliografia in enumerate(componente.get("bibliografias", [])):
            dados_bibliografia = _dados_formulario(bibliografia, list(BibliografiaForm.Meta.fields))
            bib_form = BibliografiaForm(dados_bibliografia)
            item["bibliografias"].append({"indice": bib_indice, **_resultado_formulario(bib_form, dados_bibliografia)})
        componentes.append(item)
    apendices = []
    for indice, apendice in enumerate(dados["apendices"]):
        dados_apendice = _dados_formulario(apendice, ["tipo", "titulo", "descricao"])
        form = ApendiceForm(dados_apendice)
        apendices.append({"indice": indice, **_resultado_formulario(form, dados_apendice)})
    membros = []
    for indice, membro in enumerate(dados["membros_nde"]):
        dados_membro = _dados_formulario(membro, list(MembroNDEForm.Meta.fields))
        form = MembroNDEForm(dados_membro)
        membros.append({"indice": indice, "nome": membro.get("nome"), **_resultado_formulario(form, dados_membro)})
    possui_dinamica = any(valor not in (None, "") for valor in dados["dinamica_ead"].values())
    dinamica = {"avaliada": False, "valido": True, "erros": {}}
    if possui_dinamica:
        dados_dinamica = _dados_formulario(dados["dinamica_ead"], list(DinamicaEADForm.Meta.fields))
        form = DinamicaEADForm(dados_dinamica)
        dinamica = {"avaliada": True, **_resultado_formulario(form, dados_dinamica)}

    validos = all(item["valido"] for item in resultados.values()) and all(item["valido"] and all(bib["valido"] for bib in item["bibliografias"]) for item in componentes) and all(item["valido"] for item in apendices + membros) and dinamica["valido"]
    relacoes = [
        {"componente": componente.get("nome"), "relacoes": componente.get("relacoes", [])}
        for componente in dados["componentes_curriculares"] if componente.get("relacoes")
    ]
    return {
        "pronto_para_revisao": True,
        "pronto_para_confirmacao": validos,
        "registros_foram_salvos": False,
        "formularios_ppc_e_curso": resultados,
        "componentes_curriculares": componentes,
        "apendices": apendices,
        "membros_nde": membros,
        "dinamica_ead": dinamica,
        "erros_para_confirmacao": {
            "formularios_ppc_e_curso": resultados,
            "componentes_curriculares": componentes,
            "apendices": apendices,
            "membros_nde": membros,
            "dinamica_ead": dinamica,
        },
        "pendencias_confirmacao": [
            "O Curso extraído não foi criado nem associado: o fluxo atual exige escolher/criar o Curso antes do PPC.",
            "As relações entre componentes foram preservadas por nome e só podem ser validadas após a confirmação dos componentes e a criação de seus IDs.",
        ] if relacoes else ["O Curso extraído não foi criado nem associado: o fluxo atual exige escolher/criar o Curso antes do PPC."],
        "relacoes_pendentes": relacoes,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Analisa um PPC com uma única chamada à API.")
    parser.add_argument("pdf", type=Path, help="Caminho para o PDF")
    args = parser.parse_args()
    if not args.pdf.is_file():
        parser.error(f"Arquivo não encontrado: {args.pdf}")

    texto = extrair_texto_integral(args.pdf)
    print(f"{len(texto):,} caracteres extraídos; enviando uma única requisição...")
    dados = chamar_api(montar_prompt(texto), len(texto))
    validar_estrutura(dados)
    pre_save = validar_pre_save_django(dados)

    destino = Path(__file__).parent / "resultados"
    destino.mkdir(exist_ok=True)
    arquivo_saida = destino / f"{args.pdf.stem}.json"
    arquivo_saida.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    arquivo_pre_save = destino / f"{args.pdf.stem}.pre_save.json"
    arquivo_pre_save.write_text(json.dumps(pre_save, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Análise estruturada salva em: {arquivo_saida}")
    print(f"Relatório de pré-save Django salvo em: {arquivo_pre_save}")
    print(
        f"Pronto para revisão: {pre_save['pronto_para_revisao']}; "
        f"pronto para confirmação: {pre_save['pronto_para_confirmacao']}; registros salvos: False."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
