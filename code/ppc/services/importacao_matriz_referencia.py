# ppc/services/importacao_matriz_referencia.py
from django.db import transaction
from ppc.services.eventos import registrar_evento, suspender_eventos_edicao
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
        "erros": [], "sem_mapeamento": [],
    }

    vistas = {}

    for linha in linhas:
        if linha["confianca"] == "ambigua":
            relatorio["pendentes_revisao"].append(linha)
            continue

        chave_componente = linha["codigo"] or linha.get("id_componente_interno") or f"linha-{linha['linha_origem']}"
        chave = (linha["identificador_origem"], chave_componente)
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

    if dry_run:
        return relatorio

    with transaction.atomic(), suspender_eventos_edicao():
        _persistir_pendencias(relatorio)
        for linha in relatorio["ok"]:
            matriz, _ = MatrizReferenciaCurricular.objects.get_or_create(
                identificador_origem=linha["identificador_origem"],
            )

            if linha["codigo"]:
                componente, criado = ComponenteCurricular.objects.get_or_create(
                    codigo=linha["codigo"],
                    defaults={
                        "nome": linha["nome"],
                        "tipo": "disciplina",
                        "carga_horaria_teorica": linha["carga_horaria_teorica"],
                        "carga_horaria_pratica": linha["carga_horaria_pratica"],
                        "unidade_academica_componente": "",
                        "ementa": linha.get("ementa", ""),
                        "status": "aprovado",
                    },
                )
            else:
                item_existente = None
                id_interno = linha.get("id_componente_interno")
                if id_interno and str(id_interno).isdigit():
                    item_existente = ComponenteNaMatrizReferencia.objects.filter(
                        pk=int(id_interno), matriz=matriz
                    ).select_related("componente").first()
                if item_existente:
                    componente, criado = item_existente.componente, False
                else:
                    componente = ComponenteCurricular.objects.create(
                        codigo="", nome=linha["nome"], tipo="disciplina",
                        carga_horaria_teorica=linha["carga_horaria_teorica"],
                        carga_horaria_pratica=linha["carga_horaria_pratica"],
                        unidade_academica_componente="",
                        ementa=linha.get("ementa", ""), status="aprovado",
                    )
                    criado = True

            if not criado and not componente.ementa and linha.get("ementa"):
                componente.ementa = linha["ementa"]
                componente.save(update_fields=["ementa"])

            try:
                ComponenteNaMatrizReferencia.objects.update_or_create(
                    matriz=matriz,
                    componente=componente,
                    defaults={
                        "nucleo": linha["nucleo"],
                        "periodo": linha["periodo"],
                        "natureza": linha["natureza"],
                    },
                )
            except Exception as e:
                relatorio["erros"].append({"linha": linha, "erro": str(e)})

    registrar_evento(
        "matriz_referencia_importada", identificador="importacao_matriz_referencia",
        linhas_gravadas=len(relatorio["ok"]), pendencias=len(relatorio["pendentes_revisao"]),
        erros=len(relatorio["erros"]),
    )

    return relatorio


def _persistir_pendencias(relatorio):
    tipos_map = {
        "pendentes_revisao": "ambigua",
        "duplicadas_conflitantes": "duplicada_conflitante",
    }

    identificadores = {
        linha["identificador_origem"] for linha in relatorio.get("ok", [])
    }
    identificadores.update(
        linha["identificador_origem"] for linha in relatorio.get("pendentes_revisao", [])
    )
    identificadores.update(
        item["linha_atual"]["identificador_origem"]
        for item in relatorio.get("duplicadas_conflitantes", [])
    )

    for chave_relatorio, tipo in tipos_map.items():
        if identificadores:
            ImportacaoPendencia.objects.filter(
                tipo=tipo, resolvido=False,
                identificador_origem__in=identificadores,
            ).delete()

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
