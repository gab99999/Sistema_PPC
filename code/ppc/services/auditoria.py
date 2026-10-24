EXCLUIDOS = ["atualizado_em"]  # muda em todo save; não é edição do usuário
_TIPOS = {"+": "criacao", "~": "edicao", "-": "exclusao"}


def registro_edicao():
    """Modelos rastreados -> função (registro histórico) -> (ppc_id, curso_id, matriz_id).
    Para rastrear um modelo novo: ter HistoricalRecords e entrar aqui."""
    from ppc import models as m

    def ppc_do_vinculo(h):
        return (m.ComponenteNaMatriz.objects.filter(pk=h.componente_na_matriz_id)
                .values_list("ppc_id", flat=True).first())

    def matriz_do_item(h):
        return (m.ComponenteNaMatrizReferencia.objects.filter(pk=h.item_id)
                .values_list("matriz_id", flat=True).first())

    return {
        m.Curso: lambda h: (None, h.id, None),
        m.PPC: lambda h: (h.id, h.curso_id, None),
        m.DinamicaEAD: lambda h: (h.ppc_id, None, None),
        m.ComponenteNaMatriz: lambda h: (h.ppc_id, None, None),
        m.Apendice: lambda h: (h.ppc_id, None, None),
        m.ResumoCargaHorariaPPC: lambda h: (h.ppc_id, None, None),
        m.Bibliografia: lambda h: (ppc_do_vinculo(h), None, None),
        m.RelacaoComponente: lambda h: (ppc_do_vinculo(h), None, None),
        m.MembroNDE: lambda h: (None, h.curso_id, None),
        m.VinculoUsuarioCurso: lambda h: (None, h.curso_id, None),
        m.MatrizReferenciaCurricular: lambda h: (None, h.curso_id, h.id),
        m.ComponenteNaMatrizReferencia: lambda h: (None, None, h.matriz_id),
        m.RelacaoComponenteReferencia: lambda h: (None, None, matriz_do_item(h)),
        m.ComponenteCurricular: lambda h: (None, None, None),
    }


def _escopo(modelo, h):
    from ppc.models import Curso, MatrizReferenciaCurricular, PPC

    ppc_id, curso_id, matriz_id = registro_edicao()[modelo](h)
    if ppc_id:
        achado = list(PPC.objects.filter(pk=ppc_id).values_list("curso_id", flat=True)[:1])
        if achado:
            curso_id = curso_id or achado[0]
        else:
            ppc_id = None  # PPC não existe mais (exclusão em cascata)
    if matriz_id:
        achado = list(MatrizReferenciaCurricular.objects.filter(pk=matriz_id).values_list("curso_id", flat=True)[:1])
        if achado:
            curso_id = curso_id or achado[0]
        else:
            matriz_id = None
    if curso_id and not Curso.objects.filter(pk=curso_id).exists():
        curso_id = None
    return ppc_id, curso_id, matriz_id


def _campos_alterados(modelo, h, anterior):
    """Campos que mudaram de verdade. Em campos CKEditor, só conta se o texto (sem HTML) mudou."""
    from django_ckeditor_5.fields import CKEditor5Field
    from ppc.completude import _normalizar

    delta = h.diff_against(anterior, excluded_fields=EXCLUIDOS)
    campos = []
    for mudanca in delta.changes:
        campo = modelo._meta.get_field(mudanca.field)
        if isinstance(campo, CKEditor5Field) and _normalizar(mudanca.old) == _normalizar(mudanca.new):
            continue  # só o HTML foi reformatado pelo editor
        campos.append(mudanca.field)
    return campos


def montar_evento(modelo, h, anterior):
    """Devolve um EventoEdicao (não salvo) ou None se o save não mudou nada."""
    from ppc.models import EventoEdicao

    tipo = _TIPOS[h.history_type]
    campos = []
    if tipo == "edicao" and anterior is not None:
        campos = _campos_alterados(modelo, h, anterior)
        if not campos:
            return None
    ppc_id, curso_id, matriz_id = _escopo(modelo, h)
    return EventoEdicao(
        modelo=modelo._meta.label,
        objeto_id=h.id,
        history_id=h.history_id,
        tipo=tipo,
        campos=campos,
        usuario_id=h.history_user_id,
        ppc_id=ppc_id,
        curso_id=curso_id,
        matriz_id=matriz_id,
        ocorreu_em=h.history_date,
    )