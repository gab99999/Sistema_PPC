import textwrap

from ..models import RelacaoComponente, RelacaoComponenteReferencia

LARGURA, ALTURA = 150, 60
GAP_X, GAP_Y = 56, 14
TOPO, MARGEM = 30, 10
CORES_NUCLEO = {'NC': '#dbe9ff', 'NE': '#e9f5e1'}
COR_PRE, COR_CO, COR_ERRO = '#334155', '#b45309', '#dc2626'


def _pontos(lista):
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in lista)


def _caixa(no, col, linha):
    x = MARGEM + col * (LARGURA + GAP_X)
    y = TOPO + MARGEM + linha * (ALTURA + GAP_Y)
    texto = textwrap.wrap(no['nome'], width=24)
    if len(texto) > 3:
        texto = texto[:3]
        texto[2] = texto[2][:23] + '…'
    cabecalho = " · ".join(p for p in (no['codigo'], f"{no['ch']}h") if p)
    return {
        'id': no['id'], 'col': col, 'x': x, 'y': y, 'w': LARGURA, 'h': ALTURA,
        'cabecalho': cabecalho,
        'cab_y': y + 14,
        'linhas': [{'y': y + 28 + 11 * i, 't': t} for i, t in enumerate(texto)],
        'nome_completo': no['nome'],
        'fill': CORES_NUCLEO.get(no['nucleo'], '#f3f4f6'),
        'tracejada': no['natureza'] == 'optativa',
    }


def _caminho(o, d):
    """Curva de o até d. Retorna (path, seta)."""
    yo, yd = o['y'] + ALTURA / 2, d['y'] + ALTURA / 2
    if o['col'] < d['col']:
        x1, x2 = o['x'] + LARGURA, d['x']
        dx = (x2 - x1) / 2
        path = f"M{x1},{yo:.1f} C{x1 + dx:.1f},{yo:.1f} {x2 - dx:.1f},{yd:.1f} {x2},{yd:.1f}"
        seta = [(x2, yd), (x2 - 8, yd - 4), (x2 - 8, yd + 4)]
    elif o['col'] == d['col']:
        x1 = o['x'] + LARGURA
        b = 28
        path = f"M{x1},{yo:.1f} C{x1 + b},{yo:.1f} {x1 + b},{yd:.1f} {x1},{yd:.1f}"
        seta = [(x1, yd), (x1 + 8, yd - 4), (x1 + 8, yd + 4)]
    else:
        x1, x2 = o['x'], d['x'] + LARGURA
        dx = (x1 - x2) / 2
        path = f"M{x1},{yo:.1f} C{x1 - dx:.1f},{yo:.1f} {x2 + dx:.1f},{yd:.1f} {x2},{yd:.1f}"
        seta = [(x2, yd), (x2 + 8, yd - 4), (x2 + 8, yd + 4)]
    return path, seta


def calcular_layout(nos, arestas):
    """nos: [{id, periodo, codigo, nome, ch, nucleo, natureza}]
    arestas: [{origem, destino, tipo}] — para pré-requisito, origem é o pré-requisito."""
    if not nos:
        return None

    periodos = sorted({n['periodo'] for n in nos})
    col_de = {p: i for i, p in enumerate(periodos)}
    por_col = {i: [] for i in range(len(periodos))}
    for n in sorted(nos, key=lambda n: (n['natureza'] != 'obrigatoria', n['nome'])):
        por_col[col_de[n['periodo']]].append(n)

    caixas = {}
    for col, lista in por_col.items():
        for linha, n in enumerate(lista):
            caixas[n['id']] = _caixa(n, col, linha)

    max_linhas = max(len(l) for l in por_col.values())
    largura = MARGEM * 2 + len(periodos) * LARGURA + (len(periodos) - 1) * GAP_X
    altura = TOPO + MARGEM * 2 + max_linhas * ALTURA + (max_linhas - 1) * GAP_Y

    colunas = [
        {'rotulo': f"{p}º período", 'x': MARGEM + i * (LARGURA + GAP_X)}
        for i, p in enumerate(periodos)
    ]

    vistos, saidas, erros = set(), [], 0
    for a in arestas:
        o, d = caixas.get(a['origem']), caixas.get(a['destino'])
        if not o or not d or o is d:
            continue
        co = a['tipo'] == 'co_requisito'
        chave = (frozenset((a['origem'], a['destino'])), a['tipo']) if co else (a['origem'], a['destino'], a['tipo'])
        if chave in vistos:
            continue
        vistos.add(chave)

        path, seta = _caminho(o, d)
        erro = (not co) and o['col'] >= d['col']   # pré-requisito no mesmo período ou depois
        erros += erro
        saidas.append({
            'path': path,
            'seta': None if co else _pontos(seta),
            'cor': COR_ERRO if erro else (COR_CO if co else COR_PRE),
            'tracejada': co,
        })

    return {
        'largura': largura, 'altura': altura,
        'colunas': colunas, 'caixas': list(caixas.values()),
        'arestas': saidas, 'erros': erros,
    }


def _no(id_, periodo, componente, nucleo, natureza):
    return {
        'id': id_, 'periodo': periodo, 'codigo': componente.codigo, 'nome': componente.nome,
        'ch': componente.carga_horaria_computada_total, 'nucleo': nucleo, 'natureza': natureza,
    }


def _aresta(id_componente, id_relacionado, tipo):
    if tipo == 'pre_requisito':
        # o relacionado é o pré-requisito: a seta vai dele para o componente
        return {'origem': id_relacionado, 'destino': id_componente, 'tipo': tipo}  # <- inverter se necessário
    return {'origem': id_componente, 'destino': id_relacionado, 'tipo': tipo}


def montar_fluxograma_ppc(ppc):
    vinculos = list(
        ppc.matriz_componentes.select_related('componente').filter(componente__status='aprovado')
    )
    nos = [_no(v.id, v.periodo, v.componente, v.nucleo, v.natureza) for v in vinculos]
    arestas = [
        _aresta(r.componente_na_matriz_id, r.componente_relacionado_na_matriz_id, r.tipo)
        for r in RelacaoComponente.objects.filter(componente_na_matriz__ppc=ppc)
    ]
    return calcular_layout(nos, arestas)


def montar_fluxograma_referencia(matriz):
    itens = list(matriz.componentes.select_related('componente'))
    nos = [_no(i.id, i.periodo, i.componente, i.nucleo, i.natureza) for i in itens]
    arestas = [
        _aresta(r.item_id, r.item_relacionado_id, r.tipo)
        for r in RelacaoComponenteReferencia.objects.filter(item__matriz=matriz)
    ]
    return calcular_layout(nos, arestas)


# --- cópia de relações (ver passo 6) ---

def copiar_relacoes_referencia_para_ppc(matriz, ppc):
    """Depois de aplicar a matriz ao PPC, recria as relações entre os vínculos do PPC."""
    vinculos = {v.componente_id: v for v in ppc.matriz_componentes.all()}
    criadas = 0
    for r in RelacaoComponenteReferencia.objects.filter(item__matriz=matriz).select_related('item', 'item_relacionado'):
        a = vinculos.get(r.item.componente_id)
        b = vinculos.get(r.item_relacionado.componente_id)
        if a and b:
            _, novo = RelacaoComponente.objects.get_or_create(
                componente_na_matriz=a, componente_relacionado_na_matriz=b, tipo=r.tipo
            )
            criadas += novo
    return criadas


def copiar_relacoes_entre_matrizes(origem, nova):
    """Usado ao duplicar uma matriz de referência."""
    itens = {i.componente_id: i for i in nova.componentes.all()}
    for r in RelacaoComponenteReferencia.objects.filter(item__matriz=origem).select_related('item', 'item_relacionado'):
        a = itens.get(r.item.componente_id)
        b = itens.get(r.item_relacionado.componente_id)
        if a and b:
            RelacaoComponenteReferencia.objects.get_or_create(item=a, item_relacionado=b, tipo=r.tipo)