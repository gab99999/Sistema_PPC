import re
import pdfplumber


def _remover_numeros_pagina(texto_pagina):
    linhas = texto_pagina.split('\n')
    linhas_filtradas = [
        linha for linha in linhas
        if not re.fullmatch(r'\s*\d{1,4}\s*', linha)
    ]
    return '\n'.join(linhas_filtradas)


def _dividir_por_marcadores(texto, marcadores):
    """
    Divide um texto em blocos, usando títulos exatos (cada um sozinho numa
    linha) como pontos de corte. Retorna {marcador: conteúdo até o próximo}.
    Ignora diferença de maiúsculas/minúsculas (os capítulos são renderizados
    em caixa alta no PDF via CSS, mas o texto original é normal).
    """
    padrao = re.compile(
        r'^\s*(' + '|'.join(re.escape(m) for m in marcadores) + r')\s*$',
        re.MULTILINE | re.IGNORECASE
    )
    mapa_canonico = {m.lower(): m for m in marcadores}
    ocorrencias = list(padrao.finditer(texto))
    resultado = {}
    for i, ocorrencia in enumerate(ocorrencias):
        encontrado = ocorrencia.group(1).strip()
        marcador = mapa_canonico.get(encontrado.lower(), encontrado)
        inicio = ocorrencia.end()
        fim = ocorrencias[i + 1].start() if i + 1 < len(ocorrencias) else len(texto)
        resultado[marcador] = texto[inicio:fim].strip()
    return resultado


CAPITULOS_TEXTO_SIMPLES = {
    '2 Apresentação': 'apresentacao_texto',
    '8 Estágio Curricular': 'estagio',
    '9 Trabalho de Conclusão de Curso': 'tcc',
    '10 Atividades Complementares': 'atividades_complementares',
    '11 Integração Ensino, Pesquisa e Extensão': 'politicas_integrada',
    '12 Avaliação do Processo de Ensino-Aprendizagem': 'avaliacao_ensino_aprendizagem',
    '13 Avaliação do Projeto de Curso': 'avaliacao_projeto_curso',
    '14 Qualificação de Docentes e Técnico-Administrativos': 'qualificacao',
    '17 Referências': 'bibliografias_ppc',
}

SUBSECOES_OBJETIVOS = {
    '4.1 Objetivo Geral': 'objetivo_geral',
    '4.2 Objetivos Específicos': 'objetivo_especifico',
}

SUBSECOES_PRINCIPIOS = {
    'Princípios gerais': 'principios_geral',
    'Prática profissional': 'principios_pratica_profissional',
    'Formação técnica': 'principios_formacao_tecnica',
    'Formação ética e função social': 'principios_formacao_etica_social',
    'Interdisciplinaridade': 'principios_interdisciplinaridade',
    'Articulação entre teoria e prática': 'principios_articulacao_teoria_pratica',
}


SUBSECOES_EXPECTATIVAS = {
    'Perfil do curso': 'perfil_curso',
    'Perfil e habilidades do egresso': 'perfil_habilidades',
}

SUBSECOES_REQUISITOS = {
    'Diretrizes Curriculares Nacionais do Curso': 'diretrizes_curriculares_nacionais_curso',
    'Diretrizes Curriculares Nacionais da Educação Básica': 'diretrizes_curriculares_nacionais_educacao_basica',
    'Relações étnico-raciais, história e cultura afro-brasileira e indígena': 'diretrizes_etnico_raciais_afro_indigena',
    'Educação em direitos humanos': 'diretrizes_educacao_direitos_humanos',
    'Proteção dos direitos da pessoa com TEA': 'protecao_direitos_pessoa_transtorno_espectro_autista',
    'Componente curricular de Libras': 'componente_curricular_libras',
    'Políticas de educação ambiental': 'politicas_educacao_ambiental',
    'Formação de professores da educação básica': 'diretrizes_formacao_professores_educacao_basica',
    'Acessibilidade': 'condicoes_acesso_pessoas_deficiencia_mobilidade_reduzida',
}


def _extrair_capitulos_texto(texto_completo):
    dados = {}
    principais = (
        list(CAPITULOS_TEXTO_SIMPLES.keys()) +
        ['3 Exposição de Motivos', '4 Objetivos',
         '5 Princípios Norteadores para a Formação Profissional',
         '6 Expectativas da Formação Profissional',
         '7 Estrutura Curricular',
         '15 Requisitos Legais e Normativos',
         '16 Dinâmica das Atividades (EAD)',
         '18 Apêndices']
    )
    blocos = _dividir_por_marcadores(texto_completo, principais)

    for titulo, campo in CAPITULOS_TEXTO_SIMPLES.items():
        if titulo in blocos:
            dados[campo] = blocos[titulo]

    grupos_aninhados = [
        ('4 Objetivos', SUBSECOES_OBJETIVOS),
        ('5 Princípios Norteadores para a Formação Profissional', SUBSECOES_PRINCIPIOS),
        ('6 Expectativas da Formação Profissional', SUBSECOES_EXPECTATIVAS),
        ('15 Requisitos Legais e Normativos', SUBSECOES_REQUISITOS),
    ]
    for titulo_pai, subsecoes in grupos_aninhados:
        if titulo_pai in blocos:
            sub = _dividir_por_marcadores(blocos[titulo_pai], list(subsecoes.keys()))
            for titulo, campo in subsecoes.items():
                if titulo in sub:
                    dados[campo] = sub[titulo]

    if '3 Exposição de Motivos' in blocos:
        texto_exp = blocos['3 Exposição de Motivos']
        match_tipo = re.search(r'Tipo de PPC:\s*(.+)', texto_exp)
        if match_tipo:
            tipo_bruto = match_tipo.group(1).strip().lower()
            dados['tipo_ppc'] = 'reformulacao' if 'reformul' in tipo_bruto else 'novo'
            texto_exp = re.sub(r'Tipo de PPC:.*\n?', '', texto_exp)
        dados['exposicao_motivos'] = texto_exp.strip()

    return dados


def _extrair_informacoes_gerais(pdf):
    for pagina in pdf.pages:
        for tabela in pagina.extract_tables():
            primeira_coluna = [linha[0] for linha in tabela if linha and linha[0]]
            if 'Curso' in primeira_coluna and 'Área de conhecimento' in primeira_coluna:
                return {linha[0].strip(): (linha[1] or '').strip() for linha in tabela if linha and linha[0]}
    return {}


def _mapear_informacoes_gerais(bruto):
    dados = {}
    if 'Curso' in bruto:
        dados['curso_nome'] = bruto['Curso']
    if 'Unidade acadêmica responsável' in bruto:
        dados['curso_unidade_academica'] = bruto['Unidade acadêmica responsável']
    if 'Área de conhecimento' in bruto:
        dados['curso_area_conhecimento'] = bruto['Área de conhecimento']
    if 'Modalidade / grau' in bruto:
        partes = bruto['Modalidade / grau'].split('/')
        if len(partes) == 2:
            modalidade_texto, grau_texto = [p.strip().lower() for p in partes]
            dados['modalidade'] = 'ead' if 'distân' in modalidade_texto else 'presencial'
            dados['grau_academico'] = 'licenciatura' if 'licenciat' in grau_texto else 'bacharelado'
    if 'Turno / vagas anuais' in bruto:
        partes = bruto['Turno / vagas anuais'].split('/')
        if len(partes) == 2:
            dados['turno_funcionamento'] = partes[0].strip()
            numeros = re.sub(r'\D', '', partes[1])
            if numeros:
                dados['numero_vagas_anuais'] = int(numeros)
    if 'Carga horária total' in bruto:
        numeros = re.sub(r'\D', '', bruto['Carga horária total'])
        if numeros:
            dados['carga_horaria_total'] = int(numeros)
    if 'Duração (mínima, média e máxima)' in bruto:
        numeros = re.findall(r'\d+', bruto['Duração (mínima, média e máxima)'])
        if len(numeros) == 3:
            dados['duracao_minima_semestres'] = int(numeros[0])
            dados['duracao_media_semestres'] = int(numeros[1])
            dados['duracao_maxima_semestres'] = int(numeros[2])
    return dados


def _extrair_capa(texto_completo):
    dados = {}
    for rotulo, campo in [
        ('Diretor(a):', 'diretor'), ('Vice-Diretor(a):', 'vice_diretor'),
        ('Coordenador(a) do Curso:', 'coordenador_curso'),
    ]:
        match = re.search(re.escape(rotulo) + r'\s*(.+)', texto_completo)
        if match:
            dados[campo] = match.group(1).strip().split('\n')[0]
    return dados


def extrair_dados_pdf(arquivo):
    """
    Extrai os campos de um PDF gerado pelo próprio sistema (ou que siga a
    mesma estrutura). Não extrai Estrutura Curricular — isso continua
    sendo cadastro manual depois da importação.
    """
    with pdfplumber.open(arquivo) as pdf:
        bruto_info_gerais = _extrair_informacoes_gerais(pdf)
        texto_completo = "\n".join(
        _remover_numeros_pagina(pagina.extract_text() or "") for pagina in pdf.pages
)
    dados = _mapear_informacoes_gerais(bruto_info_gerais)
    dados.update(_extrair_capa(texto_completo))
    dados.update(_extrair_capitulos_texto(texto_completo))
    return dados