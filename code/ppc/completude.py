from django.utils.html import strip_tags

from ppc.models import DinamicaEAD


def _preenchido(valor):
    return bool(strip_tags(str(valor or "")).replace("\xa0", " ").strip())


def calcular_completude_ppc(ppc):
    secoes = [
        ("Apresentação", "editar_apresentacao", ["apresentacao_texto"]),
        ("Exposição de Motivos", "editar_exposicao_motivos", ["exposicao_motivos"]),
        ("Objetivos", "editar_objetivos", ["objetivo_geral", "objetivo_especifico"]),
        ("Princípios Norteadores", "editar_principios", ["principios_geral", "principios_pratica_profissional", "principios_formacao_tecnica", "principios_formacao_etica_social", "principios_interdisciplinaridade", "principios_articulacao_teoria_pratica"]),
        ("Expectativas da Formação Profissional", "editar_expectativas", ["perfil_curso", "perfil_habilidades"]),
        ("Trabalho de Conclusão de Curso", "editar_tcc", ["tcc"]),
        ("Estágio Curricular", "editar_estagio", ["estagio"]),
        ("Atividades Complementares", "editar_atividades_complementares", ["atividades_complementares"]),
        ("Integração Ensino, Pesquisa e Extensão", "editar_politicas_integrada", ["politicas_integrada"]),
        ("Avaliação do Ensino-Aprendizagem", "editar_avaliacao_ensino", ["avaliacao_ensino_aprendizagem"]),
        ("Avaliação do Projeto de Curso", "editar_avaliacao_projeto_curso", ["avaliacao_projeto_curso"]),
        ("Qualificação", "editar_qualificacao", ["qualificacao"]),
        ("Requisitos Legais e Normativos", "editar_requisitos_legais", ["diretrizes_curriculares_nacionais_curso", "diretrizes_curriculares_nacionais_educacao_basica", "diretrizes_etnico_raciais_historia_cultura_afro_indigena", "diretrizes_educacao_direitos_humanos", "protecao_direitos_pessoa_transtorno_espectro_autista", "componente_curricular_libras", "politicas_educacao_ambiental", "diretrizes_formacao_professores_educacao_basica", "condicoes_acesso_pessoas_deficiencia_mobilidade_reduzida"]),
        ("Estrutura Curricular", "lista_componentes", ["estrutura_curricular_descricao", "estrutura_curricular_informacoes_complementares"]),
        ("Referências", "editar_referencias", ["bibliografias_ppc"]),
    ]
    if ppc.modalidade == "ead":
        secoes.insert(1, ("Informações EAD", "editar_apresentacao", ["publico_alvo_ead", "ato_integracao_uab", "ato_credenciamento_mec", "polos_ead"]))
        secoes.append(("Dinâmica EAD", "editar_dinamicas_ead", []))

    resultado = []
    for nome, url, campos in secoes:
        if nome == "Dinâmica EAD":
            try:
                campos = list(ppc.dinamica_ead._meta.fields)[2:]
                preenchida = all(_preenchido(getattr(ppc.dinamica_ead, campo.name)) for campo in campos)
            except DinamicaEAD.DoesNotExist:
                preenchida = False
        else:
            preenchida = all(_preenchido(getattr(ppc, campo)) for campo in campos)
        resultado.append({"nome": nome, "url": url, "preenchida": preenchida})

    return resultado
