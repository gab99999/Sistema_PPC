
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


@admin.register(MapeamentoImportacaoMatriz)
class MapeamentoImportacaoMatrizAdmin(admin.ModelAdmin):
    list_display = ("identificador_origem", "curso", "nome_matriz_referencia")
    search_fields = ("identificador_origem", "curso__nome")
    autocomplete_fields = ["curso"]


class ComponenteNaMatrizReferenciaInline(admin.TabularInline):
    model = ComponenteNaMatrizReferencia
    extra = 0
    fields = ("componente", "periodo", "natureza", "ordem")
    autocomplete_fields = ["componente"]


@admin.register(MatrizReferenciaCurricular)
class MatrizReferenciaCurricularAdmin(admin.ModelAdmin):
    list_display = ("curso", "nome", "atualizado_em")
    list_filter = ("curso",)
    search_fields = ("curso__nome", "nome")
    inlines = [ComponenteNaMatrizReferenciaInline]


@admin.register(ImportacaoPendencia)
class ImportacaoPendenciaAdmin(admin.ModelAdmin):
    list_display = (
        "tipo", "identificador_origem", "codigo", "nome",
        "linha_origem", "resolvido", "criado_em",
    )
    list_filter = ("tipo", "resolvido")
    search_fields = ("identificador_origem", "codigo", "nome")
    readonly_fields = ("dados_brutos", "criado_em")
    actions = ["marcar_como_resolvido"]

    @admin.action(description="Marcar selecionadas como resolvidas")
    def marcar_como_resolvido(self, request, queryset):
        atualizadas = queryset.update(resolvido=True, resolvido_em=timezone.now())
        self.message_user(request, f"{atualizadas} pendência(s) marcada(s) como resolvida(s).")

admin.site.register(PPC, SimpleHistoryAdmin)
admin.site.register(Curso, SimpleHistoryAdmin)
admin.site.register(ComponenteCurricular, SimpleHistoryAdmin)
admin.site.register(RelacaoComponente, SimpleHistoryAdmin)
admin.site.register(Bibliografia, SimpleHistoryAdmin)
admin.site.register(Apendice, SimpleHistoryAdmin)
admin.site.register(DinamicaEAD, SimpleHistoryAdmin)

