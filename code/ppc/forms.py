from django import forms
from django.core.exceptions import ValidationError
from ppc.models import PPC, Curso, DinamicaEAD, Apendice, ComponenteNaMatrizReferencia, Bibliografia, RelacaoComponente, ComponenteCurricular, MembroNDE, ComponenteNaMatriz, CineBrasilCurso, ResumoCargaHorariaPPC, VinculoUsuarioCurso, RelacaoComponenteReferencia
from django.contrib.auth.models import User, Group
from django.forms import modelformset_factory
from django.contrib.auth import get_user_model
from django.db import transaction

class ComponenteMatrizReferenciaForm(forms.ModelForm):
    """Cria o ComponenteCurricular e o vínculo na matriz de referência de uma vez."""
    nucleo = forms.ChoiceField(
        label="Núcleo", choices=ComponenteNaMatrizReferencia.NUCLEO_CHOICES, initial='NE'
    )
    natureza = forms.ChoiceField(
        label="Natureza", choices=ComponenteNaMatrizReferencia.NATUREZA_CHOICES, initial='obrigatoria'
    )
    periodo = forms.IntegerField(label="Período", min_value=1, initial=1)

    class Meta:
        model = ComponenteCurricular
        fields = [
            'codigo', 'nome', 'tipo', 'ccu',
            'carga_horaria_teorica', 'carga_horaria_pratica',
            'carga_horaria_estudante', 'carga_horaria_professor',
            'carga_horaria_acex', 'ementa',
        ]
        labels = {
            'codigo': 'Código',
            'carga_horaria_teorica': 'Carga horária teórica',
            'carga_horaria_pratica': 'Carga horária prática',
            'carga_horaria_estudante': 'Carga horária do estudante',
            'carga_horaria_professor': 'Carga horária do professor',
            'carga_horaria_acex': 'Carga horária ACEx',
        }
        widgets = {'ementa': forms.Textarea(attrs={'rows': 4})}

    field_order = [
        'codigo', 'nome', 'tipo', 'nucleo', 'natureza', 'periodo', 'ccu',
        'carga_horaria_teorica', 'carga_horaria_pratica',
        'carga_horaria_estudante', 'carga_horaria_professor',
        'carga_horaria_acex', 'ementa',
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Cada grupo de carga fica oculto conforme o tipo; a obrigatoriedade é tratada no clean()
        for nome in ('carga_horaria_teorica', 'carga_horaria_pratica',
                     'carga_horaria_estudante', 'carga_horaria_professor',
                     'carga_horaria_acex'):
            self.fields[nome].required = False
            self.fields[nome].initial = 0
        self.fields['ccu'].initial = True   # mesmo padrão do formulário antigo (Sim)

    def clean(self):
        cleaned = super().clean()
        tipo = cleaned.get('tipo')

        if tipo == 'atividade':
            cleaned['carga_horaria_teorica'] = 0
            cleaned['carga_horaria_pratica'] = 0
        else:
            cleaned['carga_horaria_teorica'] = cleaned.get('carga_horaria_teorica') or 0
            cleaned['carga_horaria_pratica'] = cleaned.get('carga_horaria_pratica') or 0
        cleaned['carga_horaria_estudante'] = cleaned.get('carga_horaria_estudante') or 0
        cleaned['carga_horaria_professor'] = cleaned.get('carga_horaria_professor') or 0
        cleaned['carga_horaria_acex'] = cleaned.get('carga_horaria_acex') or 0

        if cleaned.get('nucleo') == 'NC' and cleaned.get('natureza') != 'obrigatoria':
            self.add_error('natureza', "Componentes do Núcleo Comum são sempre de natureza obrigatória.")
        return cleaned

    @transaction.atomic
    def salvar_na_matriz(self, matriz, usuario):
        componente = self.save(commit=False)
        componente.criado_por = usuario
        componente.save()
        return ComponenteNaMatrizReferencia.objects.create(
            matriz=matriz,
            componente=componente,
            periodo=self.cleaned_data['periodo'],
            natureza=self.cleaned_data['natureza'],
            nucleo=self.cleaned_data['nucleo'],
        )

class VinculoUsuarioCursoForm(forms.ModelForm):
    class Meta:
        model = VinculoUsuarioCurso
        fields = ['usuario', 'curso']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        User = get_user_model()
        # staff já vê tudo; só faz sentido vincular usuários comuns
        self.fields['usuario'].queryset = User.objects.filter(
            is_staff=False, is_active=True
        ).order_by('username')
        self.fields['curso'].queryset = Curso.objects.order_by('nome')

class ResumoCargaHorariaPPCForm(forms.ModelForm):
    class Meta:
        model = ResumoCargaHorariaPPC
        fields = ["nucleo_livre_manual", "acex_nucleo_livre_manual", "acex_extensao_manual", "atividades_complementares_manual"]


LimitesCargaHorariaFormSet = modelformset_factory(
    Curso,
    fields=('carga_horaria_minima', 'carga_horaria_maxima'),
    extra=0,
)

class ComponenteNaMatrizForm(forms.ModelForm):
    class Meta:
        model = ComponenteNaMatriz
        fields = ['periodo', 'natureza', 'nucleo', 'grupo_licenciatura']

    def __init__(self, *args, **kwargs):
        ppc = kwargs.pop('ppc', None)
        super().__init__(*args, **kwargs)
        if ppc is None and self.instance.ppc_id:
            ppc = self.instance.ppc          # edição: pega do próprio vínculo
        if ppc is not None and ppc.grau_academico != 'licenciatura':
            self.fields.pop('grupo_licenciatura')

class ImportarPDFForm(forms.Form):
    arquivo = forms.FileField(label="Arquivo PDF do PPC", widget=forms.ClearableFileInput(attrs={"accept": "application/pdf,.pdf"}))

class ImportarPPCModeloAntigoForm(forms.Form):
    arquivo = forms.FileField(
        label="Documento do PPC (PDF)",
        help_text="PDF do PPC antigo, fora do formato do sistema.",
    )

    def clean_arquivo(self):
        arquivo = self.cleaned_data["arquivo"]
        if not arquivo.name.lower().endswith(".pdf"):
            raise ValidationError("Envie um arquivo no formato PDF.")
        inicio = arquivo.read(5)
        arquivo.seek(0)
        if inicio != b"%PDF-":
            raise ValidationError("O arquivo enviado não é um PDF válido.")
        return arquivo


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
            'codigo', 'nome', 'tipo', 'ccu',
            'carga_horaria_teorica', 'carga_horaria_pratica', 
            'carga_horaria_estudante', 'carga_horaria_professor', 'carga_horaria_acex',
            'unidade_academica_componente', 'ementa',
        ]
    def clean_carga_horaria(self):
        valor = self.cleaned_data["carga_horaria"]
        if valor % 8 != 0:
            raise forms.ValidationError("A carga horária deve ser múltipla de 8.")
        return valor


class BibliografiaForm(forms.ModelForm):
    class Meta:
        model = Bibliografia
        fields = ['tipo', 'titulo', 'autores', 'editora', 'cidade', 'ano']  # sem componente_na_matriz
class RelacaoComponenteForm(forms.ModelForm):
    class Meta:
        model = RelacaoComponente
        fields = ['componente_relacionado_na_matriz', 'tipo']

    def __init__(self, *args, ppc=None, componente_na_matriz_atual=None, **kwargs):
        super().__init__(*args, **kwargs)
        if ppc:
            qs = ComponenteNaMatriz.objects.filter(ppc=ppc).select_related('componente')
            if componente_na_matriz_atual:
                qs = qs.exclude(id=componente_na_matriz_atual.id)
            self.fields['componente_relacionado_na_matriz'].queryset = qs


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


class CursoForm(forms.ModelForm):
    class Meta:
        model = Curso
        fields = ['nome', 'cine_brasil', 'unidade_academica', 'area_conhecimento',
                  'carga_horaria_minima', 'carga_horaria_maxima']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['cine_brasil'].required = False
        if self.data.get('cine_brasil'):
            # Form sendo validado com dado enviado (POST) — o queryset de validação
            # precisa incluir o valor que veio, senão o Django rejeita como inválido
            # mesmo sendo o valor certo.
            self.fields['cine_brasil'].queryset = CineBrasilCurso.objects.filter(pk=self.data.get('cine_brasil'))
        elif self.instance.pk and self.instance.cine_brasil_id:
            self.fields['cine_brasil'].queryset = CineBrasilCurso.objects.filter(pk=self.instance.cine_brasil_id)
        else:
            self.fields['cine_brasil'].queryset = CineBrasilCurso.objects.none()

class ObjetivosForm(forms.ModelForm):
    class Meta:
        model = PPC
        fields = ['objetivo_geral', 'objetivo_especifico']


class ApresentacaoForm(forms.ModelForm):
    class Meta:
        model = PPC
        fields = ['apresentacao_texto', 'publico_alvo_ead', 'ato_integracao_uab', 'ato_credenciamento_mec', 'polos_ead'] + [
            'modalidade', 'grau_academico', 'turno_funcionamento',
            'numero_vagas_anuais',  # carga_horaria_total removido daqui
            'duracao_minima_semestres', 'duracao_media_semestres', 'duracao_maxima_semestres',
            'diretor', 'vice_diretor', 'coordenador_curso', 'vice_coordenador_curso', 'tipo_ppc', 'status', 'numero_resolucao',
        ]
    def __init__(self, *args, curso=None, usuario=None, **kwargs):
            super().__init__(*args, **kwargs)
            self.curso = curso or getattr(self.instance, 'curso', None)
            self.usuario = usuario
            if usuario is not None and not usuario.is_staff:
                self.fields['status'].choices = [
                    (valor, rotulo) for valor, rotulo in PPC.STATUS_CHOICES if valor != 'aprovado'
                ]
    
    def clean_status(self):
        status = self.cleaned_data.get('status')
        if status == 'aprovado' and self.usuario is not None and not self.usuario.is_staff:
            raise forms.ValidationError("Somente um administrador pode marcar um PPC como aprovado.")
        return status
        # clean_carga_horaria_total removido inteiro — não existe mais campo pra validar aqui


class ExposicaoMotivosForm(forms.ModelForm):
    class Meta:
        model = PPC
        fields = ['tipo_ppc', 'exposicao_motivos']


class RelacaoComponenteReferenciaForm(forms.ModelForm):
    class Meta:
        model = RelacaoComponenteReferencia
        fields = ['item', 'tipo', 'item_relacionado']
        labels = {
            'item': 'Componente',
            'tipo': 'Tipo',
            'item_relacionado': 'Tem como pré/co-requisito',
        }

    def __init__(self, *args, matriz=None, **kwargs):
        super().__init__(*args, **kwargs)
        itens = ComponenteNaMatrizReferencia.objects.filter(matriz=matriz).select_related(
            'componente'
        ).order_by('periodo', 'componente__nome')
        self.fields['item'].queryset = itens
        self.fields['item_relacionado'].queryset = itens