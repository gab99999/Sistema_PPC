from django import forms
from ppc.models import PPC
from django.contrib.auth.models import User, Group

class EditarPermissoesForm(forms.ModelForm):
    groups = forms.ModelMultipleChoiceField(
        queryset=Group.objects.all(), required=False, widget=forms.CheckboxSelectMultiple
    )
    class Meta:
        model = User
        fields = ['is_staff', 'groups']

class PPCInformacoesGeraisForm(forms.ModelForm):
    class Meta:
        model = PPC
        fields = [
            'modalidade', 'grau_academico', 'turno_funcionamento',
            'carga_horaria_total', 'numero_vagas_anuais',
            'duracao_minima_semestres', 'duracao_media_semestres', 'duracao_maxima_semestres',
            'diretor', 'vice_diretor', 'coordenador_curso', 'tipo_ppc',
        ]


class ObjetivosForm(forms.ModelForm):
    class Meta:
        model = PPC
        fields = ['objetivo_geral', 'objetivo_especifico']