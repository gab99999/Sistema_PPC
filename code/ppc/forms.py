from django import forms
from ppc.models import PPC, Curso, DinamicaEAD, Apendice, Bibliografia, RelacaoComponente, ComponenteCurricular, MembroNDE
from django.contrib.auth.models import User, Group

class ImportarPDFForm(forms.Form):
    arquivo = forms.FileField(label="Arquivo PDF do PPC")


class MembroNDEForm(forms.ModelForm):
    class Meta:
        model = MembroNDE
        fields = ['nome', 'titulacao', 'regime_trabalho', 'funcao', 'portaria_designacao', 'data_inicio', 'data_fim', 'ativo']
        widgets = {
            'data_inicio': forms.DateInput(attrs={'type': 'date'}),
            'data_fim': forms.DateInput(attrs={'type': 'date'}),
        }
class ReferenciasForm(forms.ModelForm):
    class Meta:
        model = PPC
        fields = ['bibliografias_ppc']

class ComponenteCurricularForm(forms.ModelForm):
    class Meta:
        model = ComponenteCurricular
        fields = [
            'nome', 'tipo', 'natureza', 'nucleo', 'periodo',
            'carga_horaria_teorica', 'carga_horaria_pratica', 'carga_horaria_pcc',
            'unidade_academica_componente', 'ementa',
        ]


class BibliografiaForm(forms.ModelForm):
    class Meta:
        model = Bibliografia
        fields = ['tipo', 'titulo', 'autores', 'editora', 'cidade', 'ano']


class RelacaoComponenteForm(forms.ModelForm):
    class Meta:
        model = RelacaoComponente
        fields = ['componente_relacionado', 'tipo']

    def __init__(self, *args, ppc=None, componente_atual=None, **kwargs):
        super().__init__(*args, **kwargs)
        if ppc:
            qs = ComponenteCurricular.objects.filter(ppc=ppc)
            if componente_atual:
                qs = qs.exclude(id=componente_atual.id)
            self.fields['componente_relacionado'].queryset = qs


class EstruturaCurricularForm(forms.ModelForm):
    class Meta:
        model = PPC
        fields = ['estrutura_curricular_descricao', 'estrutura_curricular_informacoes_complementares']




class ApendiceForm(forms.ModelForm):
    class Meta:
        model = Apendice
        fields = ['tipo', 'titulo', 'descricao', 'arquivo']
class DinamicaEADForm(forms.ModelForm):
    class Meta:
        model = DinamicaEAD
        fields = ['dinamica_atividades_presenciais_distancia',
                  'recuperacao_estudos_permanencia',
                  'componente_informatica_basica',
                  'atuacao_tutoria',
                  'atribuicoes_profissionais',
                  'material_didatico',
                  'ferramentas_comunicacao',
                  'carga_horaria_presencial_acompanhamento',
                  'armazenamento_gerenciamento_dados']

class RequisitosLegaisForm(forms.ModelForm):
    class Meta:
        model = PPC
        fields = ['diretrizes_curriculares_nacionais_curso',
                  'diretrizes_curriculares_nacionais_educacao_basica',
                  'diretrizes_etnico_raciais_historia_cultura_afro_indigena',
                  'diretrizes_educacao_direitos_humanos',
                  'protecao_direitos_pessoa_transtorno_espectro_autista',
                  'componente_curricular_libras',
                  'politicas_educacao_ambiental',
                  'diretrizes_formacao_professores_educacao_basica',
                  'condicoes_acesso_pessoas_deficiencia_mobilidade_reduzida']
class QualificacaoForm(forms.ModelForm):
    class Meta:
        model = PPC
        fields = ['qualificacao']
class AvalicaoProjetoCursoForm(forms.ModelForm):
    class Meta:
        model = PPC
        fields = ['avaliacao_projeto_curso']
class AvaliacaoEnsinoForm(forms.ModelForm):
    class Meta:
        model = PPC
        fields = ['avaliacao_ensino_aprendizagem']
class PoliticasIntegradaForm(forms.ModelForm):
    class Meta:
        model = PPC
        fields = ['politicas_integrada']
class AtividadesComplementaresForm(forms.ModelForm):
    class Meta:
        model = PPC
        fields = ['atividades_complementares']
class EstagioForm(forms.ModelForm):
    class Meta:
        model = PPC
        fields = ['estagio']
class TccForm(forms.ModelForm):
    class Meta:
        model = PPC
        fields = ['tcc']
class ExpectativasForm(forms.ModelForm):
    class Meta:
        model = PPC
        fields = ['perfil_curso', 'perfil_habilidades']
class PrincipiosForm(forms.ModelForm):
    class Meta:
        model = PPC
        fields = [
            'principios_geral',
            'principios_pratica_profissional',
            'principios_formacao_tecnica',
            'principios_formacao_etica_social',
            'principios_interdisciplinaridade',
            'principios_articulacao_teoria_pratica',
        ]

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
            'diretor', 'vice_diretor', 'coordenador_curso', 'tipo_ppc', 'status', 'numero_resolucao',
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
            'diretor', 'vice_diretor', 'coordenador_curso', 'tipo_ppc', 'status', 'numero_resolucao',
        ]


class ApresentacaoForm(forms.ModelForm):
    class Meta:
        model = PPC
        fields = ['apresentacao_texto', 'publico_alvo_ead', 'ato_integracao_uab', 'ato_credenciamento_mec', 'polos_ead']


class ExposicaoMotivosForm(forms.ModelForm):
    class Meta:
        model = PPC
        fields = ['tipo_ppc', 'exposicao_motivos']