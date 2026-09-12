# ppc/services/importacao_matriz_referencia.py
from django.db import transaction
from ppc.models import (
    ComponenteCurricular,
    MatrizReferenciaCurricular,
    ComponenteNaMatrizReferencia,
    MapeamentoImportacaoMatriz,
)
from ppc.models import ImportacaoPendencia

def _persistir_pendencias(relatorio):
    """Grava (ou regrava) as pendências desta rodada de import no banco,
    para revisão posterior via admin. Idempotente por rodada: apaga as
    pendências não resolvidas do mesmo tipo antes de recriar, para não
    duplicar a cada dry-run repetido."""

    tipos_map = {
        "pendentes_revisao": "ambigua",
        "duplicadas_conflitantes": "duplicada_conflitante",
        "sem_mapeamento": "sem_mapeamento",
    }

    for chave_relatorio, tipo in tipos_map.items():
        ImportacaoPendencia.objects.filter(tipo=tipo, resolvido=False).delete()

        novas = []
        for item in relatorio[chave_relatorio]:
            if tipo == "duplicada_conflitante":
                linha = item["linha_atual"]
                detalhe = (
                    f"Linha {linha['linha_origem']} conflita com linha "
                    f"{item['linha_anterior']['linha_origem']}: "
                    f"periodo/natureza diferentes para o mesmo código."
                )
            else:
                linha = item
                detalhe = linha.get("motivo_ambiguidade", "") or ""

            novas.append(ImportacaoPendencia(
                tipo=tipo,
                identificador_origem=linha["identificador_origem"],
                codigo=linha["codigo"],
                nome=linha["nome"],
                linha_origem=linha["linha_origem"],
                detalhe=detalhe,
                dados_brutos=item,
            ))

        ImportacaoPendencia.objects.bulk_create(novas)

def importar_linhas_normalizadas(linhas, dry_run=True):
    """
    Recebe a lista de linhas já normalizadas por normalizar_planilha_matriz()
    e monta um relatório. Se dry_run=False, grava no banco dentro de uma
    transação atômica — tudo ou nada.
    """
    relatorio = {
        "ok": [], "pendentes_revisao": [], "duplicadas_identicas": [],
        "duplicadas_conflitantes": [], "sem_mapeamento": [], "erros": [],
    }

    mapeamentos = {
        m.identificador_origem: m
        for m in MapeamentoImportacaoMatriz.objects.select_related("curso")
    }

    vistas = {}

    for linha in linhas:
        origem = linha["identificador_origem"]

        if origem not in mapeamentos:
            relatorio["sem_mapeamento"].append(linha)
            continue

        if linha["confianca"] == "ambigua":
            relatorio["pendentes_revisao"].append(linha)
            continue

        chave = (origem, linha["codigo"])
        if chave in vistas:
            anterior = vistas[chave]
            mesma_coisa = (
                anterior["periodo"] == linha["periodo"]
                and anterior["natureza"] == linha["natureza"]
                and anterior["carga_horaria_teorica"] == linha["carga_horaria_teorica"]
                and anterior["carga_horaria_pratica"] == linha["carga_horaria_pratica"]
            )
            if mesma_coisa:
                relatorio["duplicadas_identicas"].append(linha)
            else:
                relatorio["duplicadas_conflitantes"].append(
                    {"linha_atual": linha, "linha_anterior": anterior}
                )
            continue

        vistas[chave] = linha
        relatorio["ok"].append(linha)

    _persistir_pendencias(relatorio)

    if dry_run:
        return relatorio

    with transaction.atomic():
        for linha in relatorio["ok"]:
            mapeamento = mapeamentos[linha["identificador_origem"]]

            matriz, _ = MatrizReferenciaCurricular.objects.get_or_create(
                curso=mapeamento.curso,
                nome=mapeamento.nome_matriz_referencia,
            )

            componente, _ = ComponenteCurricular.objects.get_or_create(
                codigo=linha["codigo"],
                defaults={
                    "nome": linha["nome"],
                    "tipo": "disciplina",
                    "nucleo": linha["nucleo"],
                    "carga_horaria_teorica": linha["carga_horaria_teorica"],
                    "carga_horaria_pratica": linha["carga_horaria_pratica"],
                    "unidade_academica_componente": mapeamento.curso.unidade_academica,
                    "ementa": "",
                    "status": "aprovado",
                },
            )

            try:
                ComponenteNaMatrizReferencia.objects.update_or_create(
                    matriz=matriz,
                    componente=componente,
                    defaults={
                        "periodo": linha["periodo"],
                        "natureza": linha["natureza"],
                    },
                )
            except Exception as e:
                relatorio["erros"].append({"linha": linha, "erro": str(e)})

    return relatorio