from collections import Counter
from datetime import datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.db.models import Count, Max, Min, Q, Sum
from django.utils import timezone

from ppc.completude import SECAO_EAD_INFO, SECOES, calcular_completude_ppc
from ppc.models import EventoEdicao, EventoUso, PPC, UsoDiario

from .registro import relatorio


# ---------- helpers ----------
def _fmt(dt):
    return timezone.localtime(dt).strftime("%d/%m/%Y %H:%M") if dt else "—"


def _periodo(qs, campo, f):
    """Filtra DateTimeField pelo intervalo [data_inicio, data_fim] no horário local."""
    ini, fim = f.get("data_inicio"), f.get("data_fim")
    if ini:
        qs = qs.filter(**{f"{campo}__gte": timezone.make_aware(datetime.combine(ini, time.min))})
    if fim:
        qs = qs.filter(**{f"{campo}__lt": timezone.make_aware(datetime.combine(fim + timedelta(days=1), time.min))})
    return qs


def _periodo_data(qs, campo, f):
    """Filtra DateField pelo intervalo."""
    if f.get("data_inicio"):
        qs = qs.filter(**{f"{campo}__gte": f["data_inicio"]})
    if f.get("data_fim"):
        qs = qs.filter(**{f"{campo}__lte": f["data_fim"]})
    return qs


# ---------- Revisão ----------
@relatorio(
    "revisao_secoes_pendentes", "Seções sem revisão confirmada", "Revisão",
    "Seções de cada PPC que o NDE ainda não confirmou ou que foram alteradas depois da confirmação.",
    filtros=("curso",),
)
def revisao_secoes_pendentes(f):
    ppcs = PPC.objects.select_related("curso").order_by("curso__nome", "id")
    if f.get("curso"):
        ppcs = ppcs.filter(curso=f["curso"])
    linhas, total, completos = [], 0, 0
    for ppc in ppcs:
        total += 1
        pendentes = [s for s in calcular_completude_ppc(ppc) if not s["revisada"]]
        if not pendentes:
            completos += 1
        for s in pendentes:
            ultima = f'{s["revisado_por"] or "—"} em {_fmt(s["revisado_em"])}' if s["revisado_em"] else "—"
            linhas.append([
                ppc.curso.nome, f"#{ppc.id} ({ppc.get_status_display()})", s["nome"],
                "Pendente" if s["estado"] == "pendente" else "Alterada após a revisão",
                f'{s["campos_em_branco"]} de {s["total_campos"]}', ultima,
            ])
    return {
        "colunas": ["Curso", "PPC", "Seção", "Situação", "Campos em branco", "Última confirmação"],
        "linhas": linhas,
        "resumo": [("PPCs analisados", total), ("Com todas as seções revisadas", completos), ("Seções pendentes", len(linhas))],
    }


# ---------- PPCs ----------
@relatorio(
    "ppcs_criados", "PPCs criados", "PPCs",
    "PPCs criados no período, por curso e usuário. A origem (duplicado ou do zero) só é conhecida depois que o log foi ativado.",
    filtros=("periodo", "curso"),
)
def ppcs_criados(f):
    qs = EventoEdicao.objects.filter(modelo="ppc.PPC", tipo="criacao").select_related("usuario", "curso")
    qs = _periodo(qs, "ocorreu_em", f)
    if f.get("curso"):
        qs = qs.filter(curso=f["curso"])
    duplicados = {
        ppc_id: (meta or {}).get("origem_id")
        for ppc_id, meta in EventoUso.objects.filter(tipo="ppc_duplicado", ppc__isnull=False).values_list("ppc_id", "metadados")
    }
    inicio_log = EventoUso.objects.aggregate(m=Min("criado_em"))["m"]
    linhas = []
    for e in qs.order_by("-ocorreu_em"):
        if e.objeto_id in duplicados:
            origem = f"Duplicado do PPC #{duplicados[e.objeto_id]}"
        elif inicio_log and e.ocorreu_em >= inicio_log:
            origem = "Criado do zero"
        else:
            origem = "Anterior ao registro de origem"
        linhas.append([
            _fmt(e.ocorreu_em), e.curso.nome if e.curso else "—", f"#{e.objeto_id}",
            e.usuario.username if e.usuario else "—", origem,
        ])
    return {
        "colunas": ["Criado em", "Curso", "PPC", "Criado por", "Origem"],
        "linhas": linhas,
        "resumo": [("PPCs criados", len(linhas)), ("Duplicados", sum(1 for l in linhas if l[4].startswith("Duplicado")))],
    }


# ---------- Edições ----------
@relatorio(
    "edicoes_por_ppc", "Edições por PPC", "Edições",
    "Quantidade de edições em cada PPC de cada curso: no texto e dados do PPC, e em matriz, bibliografias, relações e demais.",
    filtros=("periodo", "curso"),
)
def edicoes_por_ppc(f):
    qs = _periodo(EventoEdicao.objects.filter(tipo="edicao", ppc__isnull=False), "ocorreu_em", f)
    if f.get("curso"):
        qs = qs.filter(ppc__curso=f["curso"])
    dados = (
        qs.values("ppc__curso__nome", "ppc_id", "ppc__criado_em")
        .annotate(
            total=Count("id"),
            no_ppc=Count("id", filter=Q(modelo="ppc.PPC")),
            usuarios=Count("usuario", distinct=True),
            ultima=Max("ocorreu_em"),
        )
        .order_by("ppc__curso__nome", "-total")
    )
    linhas = [
        [d["ppc__curso__nome"], f'#{d["ppc_id"]}', _fmt(d["ppc__criado_em"]), d["total"], d["no_ppc"],
         d["total"] - d["no_ppc"], d["usuarios"], _fmt(d["ultima"])]
        for d in dados
    ]
    return {
        "colunas": ["Curso", "PPC", "PPC criado em", "Edições", "No texto/dados do PPC", "Em matriz e demais", "Usuários", "Última edição"],
        "linhas": linhas,
        "resumo": [("PPCs editados", len(linhas)), ("Edições", sum(l[3] for l in linhas))],
    }


_ROTULO_MODELO = {
    "ppc.ComponenteNaMatriz": "Estrutura Curricular (matriz)",
    "ppc.Bibliografia": "Estrutura Curricular (matriz)",
    "ppc.RelacaoComponente": "Estrutura Curricular (matriz)",
    "ppc.Apendice": "Apêndices",
    "ppc.ResumoCargaHorariaPPC": "Quadro de carga horária",
    "ppc.DinamicaEAD": "Dinâmica EAD",
}


@relatorio(
    "edicoes_por_secao", "Edições por seção do PPC", "Edições",
    "Quantas edições atingiram cada seção. Um salvamento que muda duas seções conta nas duas.",
    filtros=("periodo", "curso"),
)
def edicoes_por_secao(f):
    qs = _periodo(EventoEdicao.objects.filter(tipo="edicao", ppc__isnull=False), "ocorreu_em", f)
    if f.get("curso"):
        qs = qs.filter(ppc__curso=f["curso"])
    campo_secao = {c: nome for _, nome, _, campos in (*SECOES, SECAO_EAD_INFO) for c in campos}
    contagem = Counter()
    for modelo, campos in qs.values_list("modelo", "campos"):
        if modelo == "ppc.PPC":
            contagem.update({campo_secao.get(c, "Informações gerais") for c in campos} or {"Informações gerais"})
        else:
            contagem.update({_ROTULO_MODELO.get(modelo, modelo)})
    return {
        "colunas": ["Seção", "Edições"],
        "linhas": [[nome, n] for nome, n in contagem.most_common()],
        "resumo": [],
    }


@relatorio(
    "edicoes_matriz_referencia", "Edições em matrizes de referência", "Matrizes de referência",
    "Por matriz: componentes adicionados, removidos e demais edições (itens, relações, dados da matriz).",
    filtros=("periodo", "curso"),
)
def edicoes_matriz_referencia(f):
    qs = _periodo(EventoEdicao.objects.filter(matriz__isnull=False), "ocorreu_em", f)
    if f.get("curso"):
        qs = qs.filter(matriz__curso=f["curso"])
    vinculo = "ppc.ComponenteNaMatrizReferencia"
    dados = (
        qs.values("matriz_id", "matriz__nome", "matriz__identificador_origem", "matriz__curso__nome")
        .annotate(
            adicionados=Count("id", filter=Q(modelo=vinculo, tipo="criacao")),
            removidos=Count("id", filter=Q(modelo=vinculo, tipo="exclusao")),
            edicoes=Count("id", filter=Q(tipo="edicao")),
            usuarios=Count("usuario", distinct=True),
            ultima=Max("ocorreu_em"),
        )
        .order_by("matriz__curso__nome", "matriz_id")
    )
    linhas = [
        [d["matriz__nome"] or d["matriz__identificador_origem"] or f'Matriz #{d["matriz_id"]}',
         d["matriz__curso__nome"] or "Sem curso", d["adicionados"], d["removidos"], d["edicoes"],
         d["usuarios"], _fmt(d["ultima"])]
        for d in dados
    ]
    return {
        "colunas": ["Matriz", "Curso", "Componentes adicionados", "Componentes removidos", "Edições", "Usuários", "Última atividade"],
        "linhas": linhas,
        "resumo": [("Matrizes com atividade", len(linhas))],
    }


# ---------- Usuários e uso ----------
@relatorio(
    "logins_por_usuario", "Logins por usuário", "Usuários e uso",
    "Quantidade de logins e último login no período. Só considera logins registrados a partir da ativação do log.",
    filtros=("periodo",),
)
def logins_por_usuario(f):
    qs = _periodo(EventoUso.objects.filter(tipo="login"), "criado_em", f)
    dados = qs.values("usuario__username").annotate(total=Count("id"), ultimo=Max("criado_em")).order_by("-total")
    linhas = [[d["usuario__username"] or "—", d["total"], _fmt(d["ultimo"])] for d in dados]
    return {
        "colunas": ["Usuário", "Logins", "Último login"],
        "linhas": linhas,
        "resumo": [("Logins", sum(l[1] for l in linhas)), ("Usuários distintos", len(linhas))],
    }


@relatorio(
    "falhas_de_login", "Falhas de login", "Usuários e uso",
    "Tentativas de login que falharam, por nome de usuário digitado.",
    filtros=("periodo",),
)
def falhas_de_login(f):
    qs = _periodo(EventoUso.objects.filter(tipo="login_falhou"), "criado_em", f)
    dados = qs.values("identificador").annotate(total=Count("id"), ultima=Max("criado_em")).order_by("-total")
    linhas = [[d["identificador"] or "—", d["total"], _fmt(d["ultima"])] for d in dados]
    return {
        "colunas": ["Usuário digitado", "Falhas", "Última falha"],
        "linhas": linhas,
        "resumo": [("Falhas", sum(l[1] for l in linhas))],
    }


@relatorio(
    "usuarios_sem_login", "Usuários sem login no período", "Usuários e uso",
    "Usuários ativos sem nenhum login registrado no período. Só considera logins registrados a partir da ativação do log.",
    filtros=("periodo", "curso"),
)
def usuarios_sem_login(f):
    logados = _periodo(EventoUso.objects.filter(tipo="login", usuario__isnull=False), "criado_em", f).values("usuario_id")
    usuarios = get_user_model().objects.filter(is_active=True).exclude(pk__in=logados)
    if f.get("curso"):
        usuarios = usuarios.filter(vinculos_curso__curso=f["curso"])
    usuarios = usuarios.order_by("username").prefetch_related("vinculos_curso__curso")
    linhas = [
        [u.username, "DAA" if u.is_staff else "NDE",
         ", ".join(v.curso.nome for v in u.vinculos_curso.all()) or "—", _fmt(u.last_login)]
        for u in usuarios
    ]
    return {
        "colunas": ["Usuário", "Perfil", "Cursos", "Último login (Django)"],
        "linhas": linhas,
        "resumo": [("Usuários sem login", len(linhas))],
    }


@relatorio(
    "uso_por_usuario_dia", "Atividade por usuário e dia", "Usuários e uso",
    "Em cada dia, quantas telas o usuário abriu e em que faixa de horário.",
    filtros=("periodo",),
)
def uso_por_usuario_dia(f):
    qs = _periodo_data(UsoDiario.objects.all(), "data", f)
    dados = (
        qs.values("usuario__username", "data")
        .annotate(paginas=Sum("contagem"), primeira=Min("hora"), ultima=Max("hora"), horas=Count("hora", distinct=True))
        .order_by("-data", "usuario__username")
    )
    linhas = [
        [d["usuario__username"], d["data"].strftime("%d/%m/%Y"), d["paginas"],
         f'{d["primeira"]:02d}h–{d["ultima"]:02d}h', d["horas"]]
        for d in dados
    ]
    return {
        "colunas": ["Usuário", "Dia", "Telas abertas", "Primeira–última hora", "Horas distintas"],
        "linhas": linhas,
        "resumo": [("Combinações usuário/dia", len(linhas))],
    }


@relatorio(
    "uso_por_usuario", "Uso por usuário", "Usuários e uso",
    "Telas abertas e dias ativos de cada usuário no período.",
    filtros=("periodo",),
)
def uso_por_usuario(f):
    qs = _periodo_data(UsoDiario.objects.all(), "data", f)
    dados = (
        qs.values("usuario__username")
        .annotate(paginas=Sum("contagem"), dias=Count("data", distinct=True), ultimo=Max("data"))
        .order_by("-paginas")
    )
    linhas = [[d["usuario__username"], d["paginas"], d["dias"], d["ultimo"].strftime("%d/%m/%Y")] for d in dados]
    return {
        "colunas": ["Usuário", "Telas abertas", "Dias ativos", "Último dia"],
        "linhas": linhas,
        "resumo": [("Usuários ativos", len(linhas)), ("Telas abertas", sum(l[1] for l in linhas))],
    }


@relatorio(
    "uso_por_tela", "Telas mais usadas", "Usuários e uso",
    "Quantas vezes cada tela foi aberta e por quantos usuários.",
    filtros=("periodo",),
)
def uso_por_tela(f):
    qs = _periodo_data(UsoDiario.objects.all(), "data", f)
    dados = qs.values("url_name").annotate(paginas=Sum("contagem"), usuarios=Count("usuario", distinct=True)).order_by("-paginas")
    return {
        "colunas": ["Tela (nome da URL)", "Vezes aberta", "Usuários"],
        "linhas": [[d["url_name"], d["paginas"], d["usuarios"]] for d in dados],
        "resumo": [],
    }


@relatorio(
    "uso_por_hora", "Uso por horário do dia", "Usuários e uso",
    "Telas abertas em cada hora do dia (horário local), para ver os horários de pico.",
    filtros=("periodo",),
)
def uso_por_hora(f):
    qs = _periodo_data(UsoDiario.objects.all(), "data", f)
    dados = qs.values("hora").annotate(paginas=Sum("contagem"), usuarios=Count("usuario", distinct=True)).order_by("hora")
    return {
        "colunas": ["Hora", "Telas abertas", "Usuários"],
        "linhas": [[f'{d["hora"]:02d}h', d["paginas"], d["usuarios"]] for d in dados],
        "resumo": [],
    }