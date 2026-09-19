# ppc/services/importacao_matriz_referencia.py
from django.db import transaction
from ppc.models import (
    ComponenteCurricular,
    MatrizReferenciaCurricular,
    ComponenteNaMatrizReferencia,
    ImportacaoPendencia,
)


def importar_linhas_normalizadas(linhas, dry_run=True):
    relatorio = {
        "ok": [], "pendentes_revisao": [],
        "duplicadas_identicas": [], "duplicadas_conflitantes": [],
        "erros": [],
    }

    vistas = {}

    for linha in linhas:
        if linha["confianca"] == "ambigua":
            relatorio["pendentes_revisao"].append(linha)
            continue

        chave = (linha["identificador_origem"], linha["codigo"])
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
            matriz, _ = MatrizReferenciaCurricular.objects.get_or_create(
                identificador_origem=linha["identificador_origem"],
            )

            componente, criado = ComponenteCurricular.objects.get_or_create(
                codigo=linha["codigo"],
                defaults={
                    "nome": linha["nome"],
                    "tipo": "disciplina",
                    "nucleo": linha["nucleo"],
                    "carga_horaria_teorica": linha["carga_horaria_teorica"],
                    "carga_horaria_pratica": linha["carga_horaria_pratica"],
                    "unidade_academica_componente": "",
                    "ementa": linha.get("ementa", ""),
                    "status": "aprovado",
                },
            )

            if not criado and not componente.ementa and linha.get("ementa"):
                componente.ementa = linha["ementa"]
                componente.save(update_fields=["ementa"])

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


def _persistir_pendencias(relatorio):
    tipos_map = {
        "pendentes_revisao": "ambigua",
        "duplicadas_conflitantes": "duplicada_conflitante",
    }

    for chave_relatorio, tipo in tipos_map.items():
        ImportacaoPendencia.objects.filter(tipo=tipo, resolvido=False).delete()

        novas = []
        for item in relatorio[chave_relatorio]:
            if tipo == "duplicada_conflitante":
                linha = item["linha_atual"]
                detalhe = (
                    f"Linha {linha['linha_origem']} conflita com linha "
                    f"{item['linha_anterior']['linha_origem']}."
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