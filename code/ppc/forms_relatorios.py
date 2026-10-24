from django import forms

from .models import Curso


class FiltroRelatorioForm(forms.Form):
    data_inicio = forms.DateField(label="De", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    data_fim = forms.DateField(label="Até", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    curso = forms.ModelChoiceField(
        queryset=Curso.objects.order_by("nome"), label="Curso", required=False, empty_label="Todos os cursos",
    )

    def __init__(self, *args, usa=(), **kwargs):
        super().__init__(*args, **kwargs)
        if "periodo" not in usa:
            del self.fields["data_inicio"]
            del self.fields["data_fim"]
        if "curso" not in usa:
            del self.fields["curso"]

    def clean(self):
        dados = super().clean()
        ini, fim = dados.get("data_inicio"), dados.get("data_fim")
        if ini and fim and fim < ini:
            self.add_error("data_fim", "A data final não pode ser anterior à inicial.")
        return dados