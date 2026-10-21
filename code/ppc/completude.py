import hashlib

from django.utils.html import strip_tags

from ppc.models import DinamicaEAD, RevisaoSecaoPPC


def _normalizar(valor):
    # None vira vazio; 0 e False não são "em branco" (importa quando houver campos numéricos)
    texto = "" if valor is None else str(valor)
    return " ".join(strip_tags(texto).replace("\xa0", " ").split())


def _preenchido(valor):
    return bool(_normalizar(valor))


# (chave, nome, nome da URL, campos do PPC). A chave nunca deve mudar depois de em uso.
SECOES = [
    ("apresentacao", "Apresentação", "editar_apresentacao", ["apresentacao_texto"]),
    ("exposicao_motivos", "Exposição de Motivos", "editar_exposicao_motivos", ["exposicao_motivos"]),
    ("objetivos", "Objetivos", "editar_objetivos", ["objetivo_geral", "objetivo_especifico"]),
    ("principios", "Princípios Norteadores", "editar_principios", ["principios_geral", "principios_pratica_profissional", "principios_formacao_tecnica", "principios_formacao_etica_social", "principios_interdisciplinaridade", "principios_articulacao_teoria_pratica"]),
    ("expectativas", "Expectativas da Formação Profissional", "editar_expectativas", ["perfil_curso", "perfil_habilidades"]),
    ("tcc", "Trabalho de Conclusão de Curso", "editar_tcc", ["tcc"]),
    ("estagio", "Estágio Curricular", "editar_estagio", ["estagio"]),
    ("atividades_complementares", "Atividades Complementares", "editar_atividades_complementares", ["atividades_complementares"]),
    ("politicas_integrada", "Integração Ensino, Pesquisa e Extensão", "editar_politicas_integrada", ["politicas_integrada"]),
    ("avaliacao_ensino", "Avaliação do Ensino-Aprendizagem", "editar_avaliacao_ensino", ["avaliacao_ensino_aprendizagem"]),
    ("avaliacao_projeto", "Avaliação do Projeto de Curso", "editar_avaliacao_projeto_curso", ["avaliacao_projeto_curso"]),
    ("qualificacao", "Qualificação", "editar_qualificacao", ["qualificacao"]),
    ("requisitos_legais", "Requisitos Legais e Normativos", "editar_requisitos_legais", ["diretrizes_curriculares_nacionais_curso", "diretrizes_curriculares_nacionais_educacao_basica", "diretrizes_etnico_raciais_historia_cultura_afro_indigena", "diretrizes_educacao_direitos_humanos", "protecao_direitos_pessoa_transtorno_espectro_autista", "componente_curricular_libras", "politicas_educacao_ambiental", "diretrizes_formacao_professores_educacao_basica", "condicoes_acesso_pessoas_deficiencia_mobilidade_reduzida"]),
    ("estrutura_curricular", "Estrutura Curricular", "lista_componentes", ["estrutura_curricular_descricao", "estrutura_curricular_informacoes_complementares"]),
    ("referencias", "Referências", "editar_referencias", ["bibliografias_ppc"]),
]
SECAO_EAD_INFO = ("informacoes_ead", "Informações EAD", "editar_apresentacao",
                  ["publico_alvo_ead", "ato_integracao_uab", "ato_credenciamento_mec", "polos_ead"])
SECAO_EAD_DINAMICA = ("dinamica_ead", "Dinâmica EAD", "editar_dinamicas_ead", None)


def secoes_do_ppc(ppc):
    secoes = list(SECOES)
    if ppc.modalidade == "ead":
        secoes.insert(1, SECAO_EAD_INFO)
        secoes.append(SECAO_EAD_DINAMICA)
    return secoes


def _valores(ppc, campos):
    if campos is None:  # Dinâmica EAD: campos do model relacionado
        campos_modelo = list(DinamicaEAD._meta.fields)[2:]
        try:
            dinamica = ppc.dinamica_ead
        except DinamicaEAD.DoesNotExist:
            return [""] * len(campos_modelo)   # ainda não existe: todos em branco
        return [getattr(dinamica, f.name) for f in campos_modelo]
    return [getattr(ppc, c) for c in campos]


def _hash(valores):
    texto = "\x1f".join(_normalizar(v) for v in valores)
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def calcular_completude_ppc(ppc):
    revisoes = {r.secao: r for r in ppc.revisoes_secao.select_related("revisado_por")}
    resultado = []
    for chave, nome, url, campos in secoes_do_ppc(ppc):
        valores = _valores(ppc, campos)
        em_branco = sum(1 for v in valores if not _preenchido(v))
        revisao = revisoes.get(chave)
        if revisao is None:
            estado = "pendente"
        elif revisao.conteudo_hash != _hash(valores):
            estado = "desatualizada"
        else:
            estado = "revisada"
        resultado.append({
            "chave": chave,
            "nome": nome,
            "url": url,
            "preenchida": em_branco == 0,
            "campos_em_branco": em_branco,
            "total_campos": len(valores),
            "estado": estado,
            "revisada": estado == "revisada",
            "revisado_por": revisao.revisado_por if revisao else None,
            "revisado_em": revisao.revisado_em if revisao else None,
        })
    return resultado


def confirmar_revisao(ppc, chaves, usuario):
    por_chave = {s[0]: s for s in secoes_do_ppc(ppc)}
    for chave in chaves:
        secao = por_chave.get(chave)
        if secao is None:
            continue
        RevisaoSecaoPPC.objects.update_or_create(
            ppc=ppc, secao=chave,
            defaults={
                "conteudo_hash": _hash(_valores(ppc, secao[3])),
                "revisado_por": usuario,
            },
        )


def revisao_completa(ppc):
    return all(s["revisada"] for s in calcular_completude_ppc(ppc))