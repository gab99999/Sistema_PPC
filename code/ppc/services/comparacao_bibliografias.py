"""Diferenças de bibliografia entre uma matriz de referência e um PPC."""

import hashlib

from ppc.management.commands.reconciliar_bibliografias import normalizar_texto


def _texto_chave(bibliografia):
    return normalizar_texto(bibliografia.titulo), normalizar_texto(bibliografia.autores)


def _obra_chave(bibliografia):
    if bibliografia.referencia_id:
        return "biblioteca", bibliografia.referencia_id
    return "manual", *_texto_chave(bibliografia)


def _chave_operacao(acao, atual=None, fonte=None):
    def estado(bib):
        if bib is None:
            return None
        return (
            bib.pk, bib.referencia_id, bib.tipo, bib.titulo, bib.autores,
            bib.editora, bib.cidade, bib.ano,
        )
    digest = hashlib.sha256(repr((estado(atual), estado(fonte))).encode("utf-8")).hexdigest()[:12]
    ids = "-".join(str(b.pk) for b in (atual, fonte) if b is not None)
    return f"{acao}-{ids}-{digest}"


def calcular_operacoes_bibliografia(item_referencia, item_ppc=None):
    """Produz operações determinísticas, sem modificar nenhum registro."""
    fontes = list(item_referencia.bibliografias.all().order_by("pk"))
    atuais = list(item_ppc.bibliografias.all().order_by("pk")) if item_ppc else []

    # Linhas repetidas na matriz não devem criar cópias repetidas no PPC.
    unicas = []
    vistos = set()
    for fonte in fontes:
        chave = (_obra_chave(fonte), fonte.tipo)
        if chave not in vistos:
            vistos.add(chave)
            unicas.append(fonte)
    fontes = unicas

    fontes_pendentes = set(range(len(fontes)))
    atuais_pendentes = set(range(len(atuais)))
    operacoes = []

    def adicionar(acao, atual=None, fonte=None):
        if acao == "adicionar":
            chave = _chave_operacao("add", fonte=fonte)
            rotulo = f"Adicionar {fonte.get_tipo_display()}: {fonte.titulo} — {fonte.autores}"
        elif acao == "remover":
            chave = _chave_operacao("remove", atual=atual)
            rotulo = f"Remover {atual.get_tipo_display()}: {atual.titulo} — {atual.autores}"
        elif acao == "alterar_tipo":
            chave = _chave_operacao("type", atual=atual, fonte=fonte)
            rotulo = f"Alterar para {fonte.get_tipo_display()}: {fonte.titulo} — {fonte.autores}"
        else:
            chave = _chave_operacao("replace", atual=atual, fonte=fonte)
            rotulo = f"Substituir por {fonte.get_tipo_display()} da Biblioteca: {fonte.titulo} — {fonte.autores}"
        operacoes.append({
            "key": chave, "acao": acao, "atual": atual, "fonte": fonte,
            "rotulo": rotulo,
        })

    # Mesmo identificador de obra e mesmo tipo: já está sincronizada.
    for i, fonte in enumerate(fontes):
        for j in sorted(atuais_pendentes):
            atual = atuais[j]
            if atual.tipo == fonte.tipo and _obra_chave(atual) == _obra_chave(fonte):
                fontes_pendentes.discard(i)
                atuais_pendentes.discard(j)
                break

    # Mesma obra vinculada à Biblioteca, ou mesmo registro manual: altera o
    # tipo como uma única operação (remove + cria para respeitar imutabilidade).
    for i in sorted(fontes_pendentes):
        fonte = fontes[i]
        for j in sorted(atuais_pendentes):
            atual = atuais[j]
            mesma_obra = (
                bool(fonte.referencia_id and atual.referencia_id and fonte.referencia_id == atual.referencia_id)
                or (not fonte.referencia_id and not atual.referencia_id and _texto_chave(fonte) == _texto_chave(atual))
            )
            if mesma_obra:
                adicionar("alterar_tipo", atual, fonte)
                fontes_pendentes.discard(i)
                atuais_pendentes.discard(j)
                break

    # Um registro manual correspondente a uma obra catalogada é substituído.
    for i in sorted(fontes_pendentes):
        fonte = fontes[i]
        for j in sorted(atuais_pendentes):
            atual = atuais[j]
            if (
                bool(fonte.referencia_id) != bool(atual.referencia_id)
                and _texto_chave(fonte) == _texto_chave(atual)
            ):
                adicionar("substituir", atual, fonte)
                fontes_pendentes.discard(i)
                atuais_pendentes.discard(j)
                break

    for j in sorted(atuais_pendentes):
        adicionar("remover", atuais[j])
    for i in sorted(fontes_pendentes):
        adicionar("adicionar", fonte=fontes[i])

    return operacoes


def resumir_operacoes(operacoes):
    return {
        "adicionar": sum(op["acao"] == "adicionar" for op in operacoes),
        "remover": sum(op["acao"] == "remover" for op in operacoes),
        "alterar_tipo": sum(op["acao"] == "alterar_tipo" for op in operacoes),
        "substituir": sum(op["acao"] == "substituir" for op in operacoes),
    }
