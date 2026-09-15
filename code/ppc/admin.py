from django.contrib import admin
from .models import Curso, PPC, ComponenteCurricular, RelacaoComponente, Bibliografia, Apendice, DinamicaEAD, models
from simple_history.admin import SimpleHistoryAdmin
from django.contrib import admin
from django.utils import timezone
from ppc.models import (
    MapeamentoImportacaoMatriz,
    MatrizReferenciaCurricular,
    ComponenteNaMatrizReferencia,
    ImportacaoPendencia,
)
# ppc/admin.py — adicionar dentro de ImportacaoPendenciaAdmin
from django.db import transaction
from ppc.services.resolucao_pendencias import resolver_pendencia_ambigua


@admin.register(ImportacaoPendencia)
class ImportacaoPendenciaAdmin(admin.ModelAdmin):
    list_display = (
        "tipo", "identificador_origem", "codigo", "nome",
        "linha_origem", "resolvido", "criado_em",
    )
    list_filter = ("tipo", "resolvido")
    search_fields = ("identificador_origem", "codigo", "nome", "detalhe")
    readonly_fields = ("dados_brutos", "criado_em")
    actions = ["marcar_como_resolvido", "resolver_como_obrigatoria", "resolver_como_optativa"]

    @admin.action(description="Marcar selecionadas como resolvidas (sem criar vínculo)")
    def marcar_como_resolvido(self, request, queryset):
        atualizadas = queryset.update(resolvido=True, resolvido_em=timezone.now())
        self.message_user(request, f"{atualizadas} pendência(s) marcada(s) como resolvida(s).")

    @admin.action(description="Resolver selecionadas como Obrigatória")
    def resolver_como_obrigatoria(self, request, queryset):
        self._resolver_em_lote(request, queryset, "obrigatoria")

    @admin.action(description="Resolver selecionadas como Optativa")
    def resolver_como_optativa(self, request, queryset):
        self._resolver_em_lote(request, queryset, "optativa")

    def _resolver_em_lote(self, request, queryset, natureza):
        resolvidas = 0
        ignoradas = 0
        with transaction.atomic():
            for pendencia in queryset.filter(tipo="ambigua", resolvido=False):
                if resolver_pendencia_ambigua(pendencia, natureza):
                    resolvidas += 1
                else:
                    ignoradas += 1

        mensagem = f"{resolvidas} pendência(s) resolvida(s) como {natureza}."
        if ignoradas:
            mensagem += f" {ignoradas} ignorada(s) — núcleo também indefinido, precisa revisão manual direta."
        self.message_user(request, mensagem)


@admin.register(Curso)
class CursoAdmin(SimpleHistoryAdmin):
    search_fields = ["nome"]


@admin.register(ComponenteCurricular)
class ComponenteCurricularAdmin(SimpleHistoryAdmin):
    search_fields = ["codigo", "nome"]


@admin.register(MapeamentoImportacaoMatriz)
class MapeamentoImportacaoMatrizAdmin(admin.ModelAdmin):
    list_display = ("identificador_origem", "curso", "nome_matriz_referencia", "observacao")
    list_filter = ("curso",)  # None aparece como "-" no filtro, ajuda a isolar os pendentes
    search_fields = ("identificador_origem", "curso__nome")
    autocomplete_fields = ["curso"]


class ComponenteNaMatrizReferenciaInline(admin.TabularInline):
    model = ComponenteNaMatrizReferencia
    extra = 0
    fields = ("componente", "periodo", "natureza", "ordem")
    autocomplete_fields = ["componente"]


@admin.register(MatrizReferenciaCurricular)
class MatrizReferenciaCurricularAdmin(admin.ModelAdmin):
    list_display = ("__str__", "curso", "identificador_origem", "atualizado_em")
    list_filter = ("curso",)  # filtra por "-" pra achar as sem curso ainda
    search_fields = ("curso__nome", "nome", "identificador_origem")
    autocomplete_fields = ["curso"]
    inlines = [ComponenteNaMatrizReferenciaInline]





admin.site.register(PPC, SimpleHistoryAdmin)
admin.site.register(RelacaoComponente, SimpleHistoryAdmin)
admin.site.register(Bibliografia, SimpleHistoryAdmin)
admin.site.register(Apendice, SimpleHistoryAdmin)
admin.site.register(DinamicaEAD, SimpleHistoryAdmin)