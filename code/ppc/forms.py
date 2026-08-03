from django import forms
from ppc.models import PPC, Curso
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

class CursoForm(forms.ModelForm):
    class Meta:
        model = Curso
        fields = ['nome', 'unidade_academica', 'area_conhecimento']

class ObjetivosForm(forms.ModelForm):
    class Meta:
        model = PPC
        fields = ['objetivo_geral', 'objetivo_especifico']

class InformacoesGeraisForm(forms.ModelForm):
    class Meta:
        model = PPC
        fields = [
            'modalidade', 'grau_academico', 'turno_funcionamento',
            'carga_horaria_total', 'numero_vagas_anuais',
            'duracao_minima_semestres', 'duracao_media_semestres', 'duracao_maxima_semestres',
            'diretor', 'vice_diretor', 'coordenador_curso',
        ]


class ApresentacaoForm(forms.ModelForm):
    class Meta:
        model = PPC
        fields = ['apresentacao_texto', 'publico_alvo_ead', 'ato_integracao_uab', 'ato_credenciamento_mec', 'polos_ead']


class ExposicaoMotivosForm(forms.ModelForm):
    class Meta:
        model = PPC
        fields = ['tipo_ppc', 'exposicao_motivos']