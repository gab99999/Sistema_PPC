import csv
import io

from django.contrib.admin.views.decorators import staff_member_required
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.contrib.auth.decorators import login_required

from .forms_relatorios import FiltroRelatorioForm
from .services.relatorios import RELATORIOS, agrupados


@login_required
def indice_relatorios(request):
    return render(request, "ppc/relatorios/indice.html", {"grupos": agrupados()})


@login_required
def ver_relatorio(request, chave):
    rel = RELATORIOS.get(chave)
    if rel is None:
        raise Http404
    form = FiltroRelatorioForm(request.GET, usa=rel.filtros)  # sempre "bound": todos os filtros são opcionais
    resultado = rel.funcao(form.cleaned_data) if form.is_valid() else None

    if resultado is not None and request.GET.get("formato") == "csv":
        buffer = io.StringIO()
        escritor = csv.writer(buffer, delimiter=";")  # ";" abre direto no Excel em pt-BR
        escritor.writerow(resultado["colunas"])
        escritor.writerows(resultado["linhas"])
        resposta = HttpResponse("\ufeff" + buffer.getvalue(), content_type="text/csv; charset=utf-8")
        resposta["Content-Disposition"] = f'attachment; filename="{chave}.csv"'
        return resposta

    return render(request, "ppc/relatorios/relatorio.html", {"rel": rel, "form": form, "resultado": resultado})