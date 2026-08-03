# ppc/models.py
from django.db import models
from django_ckeditor_5.fields import CKEditor5Field
from django.utils import timezone
from simple_history.models import HistoricalRecords

class Curso(models.Model):
    nome = models.CharField(max_length=200)
    unidade_academica = models.CharField(max_length=200)
    area_conhecimento = models.CharField(max_length=200)  # áreas CAPES

    history = HistoricalRecords()

    def __str__(self):
        return self.nome


class PPC(models.Model):
    TIPO_PPC_CHOICES = [
        ('novo', 'Curso Novo'),
        ('reformulacao', 'Reformulação Curricular'),
    ]
    MODALIDADE_CHOICES = [
        ('presencial', 'Presencial'),
        ('ead', 'A Distância'),
    ]
    GRAU_CHOICES = [
        ('bacharelado', 'Bacharelado'),
        ('licenciatura', 'Licenciatura'),
    ]
    STATUS_CHOICES = [
        ('rascunho', 'Rascunho'),
        ('em_revisao', 'Em Revisão'),
        ('aprovado', 'Aprovado'),
    ]

    curso = models.ForeignKey(Curso, on_delete=models.CASCADE, related_name='ppcs')

    # -- Informações Gerais --
    modalidade = models.CharField(max_length=20, choices=MODALIDADE_CHOICES)
    grau_academico = models.CharField(max_length=20, choices=GRAU_CHOICES)
    turno_funcionamento = models.CharField(max_length=50)
    carga_horaria_total = models.PositiveIntegerField(help_text="em horas")
    numero_vagas_anuais = models.PositiveIntegerField()
    duracao_minima_semestres = models.PositiveIntegerField()
    duracao_media_semestres = models.PositiveIntegerField()
    duracao_maxima_semestres = models.PositiveIntegerField()
    diretor = models.CharField(max_length=200)
    vice_diretor = models.CharField(max_length=200)
    coordenador_curso = models.CharField(max_length=200)

    # -- Datas --
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='rascunho')

    # -- Campos condicionais (só para EAD) --
    publico_alvo_ead = CKEditor5Field(blank=True, config_name='default')
    ato_integracao_uab = CKEditor5Field(blank=True, config_name='default')
    ato_credenciamento_mec = CKEditor5Field(blank=True, config_name='default')
    polos_ead = CKEditor5Field(blank=True, config_name='default')

    # -- Apresentação (texto narrativo) --
    apresentacao_texto = CKEditor5Field(blank=True, config_name='default')

    # -- Exposição de Motivos --
    tipo_ppc = models.CharField(max_length=20, choices=TIPO_PPC_CHOICES)
    exposicao_motivos = CKEditor5Field(blank=True, config_name='default')

    # -- Objetivos --
    objetivo_geral = CKEditor5Field(blank=True, config_name='default')
    objetivo_especifico = CKEditor5Field(blank=True, config_name='default')

    # -- Princípios Norteadores para a Formação Profissional --
    principios_geral = CKEditor5Field(blank=True, config_name='default')
    principios_pratica_profissional = CKEditor5Field(blank=True, config_name='default')
    principios_formacao_tecnica = CKEditor5Field(blank=True, config_name='default')
    principios_formacao_etica_social = CKEditor5Field(blank=True, config_name='default')
    principios_interdisciplinaridade = CKEditor5Field(blank=True, config_name='default')
    principios_articulacao_teoria_pratica = CKEditor5Field(blank=True, config_name='default')

    # -- Expectativas da Formação Profissional --
    perfil_curso = CKEditor5Field(blank=True, config_name='default')
    perfil_habilidades = CKEditor5Field(blank=True, config_name='default')

    # -- Trabalho de Conclusão de Curso --
    tcc = CKEditor5Field(blank=True, config_name='default')

    # -- Detalhes sobre Política e Gestão do Estágio Obrigátorio e Não Obrigátorio
    estagio = CKEditor5Field(blank=True, config_name='default')

    # -- Atividades Complementares do Curso --
    atividades_complementares = CKEditor5Field(blank=True, config_name='default')

    # -- Integração de Ensino, Pesquisa e Extensão --
    politicas_integrada = CKEditor5Field(blank=True, config_name='default')

    # -- Avaliação de Processo de Ensino e Aprendizagem --
    avaliacao_ensino_aprendigem = CKEditor5Field(blank=True, config_name='default')

    # -- Avaliação do Projeto de Curso -- 
    avaliacao_projeto_curso = CKEditor5Field(blank=True, config_name='default')

    # -- Qualificação de docentes e técnico-administrativos --
    qualificacao = CKEditor5Field(blank=True, config_name='default')

    # -- Requisitos legais e Normativos Obrigátorios --
    diretrizes_curriculares_nacionais_curso = CKEditor5Field(blank=True, config_name='default')  
    diretrizes_curriculares_nacionais_educacao_basica = CKEditor5Field(blank=True, config_name='default')
    diretrizes_etnico_raciais_historia_cultura_afro_indigena = CKEditor5Field(blank=True, config_name='default')
    diretrizes_educacao_direitos_humanos = CKEditor5Field(blank=True, config_name='default')
    protecao_direitos_pessoa_transtorno_espectro_autista = CKEditor5Field(blank=True, config_name='default')
    componente_curricular_libras = CKEditor5Field(blank=True, config_name='default')
    politicas_educacao_ambiental = CKEditor5Field(blank=True, config_name='default')
    diretrizes_formacao_professores_educacao_basica = CKEditor5Field(blank=True, config_name='default')
    condicoes_acesso_pessoas_deficiencia_mobilidade_reduzida = CKEditor5Field(blank=True, config_name='default')

    # -- Biblografias do PPC --
    bibliografias_ppc = CKEditor5Field(blank=True, config_name='default')

    # -- Estrutura Curricular --
    estrutura_curricular_descricao = CKEditor5Field(blank=True, config_name='default')
    estrutura_curricular_informacoes_complementares = CKEditor5Field(blank=True, config_name='default')

    history = HistoricalRecords()

    def __str__(self):
        return f"PPC - {self.curso.nome}"
    
class DinamicaEAD(models.Model):
    ppc = models.OneToOneField(PPC,on_delete=models.CASCADE,related_name="dinamica_ead")

    dinamica_atividades_presenciais_distancia = CKEditor5Field(blank=True, config_name='default')
    recuperacao_estudos_permanencia = CKEditor5Field(blank=True, config_name='default')
    componente_informatica_basica = CKEditor5Field(blank=True, config_name='default')
    atuacao_tutoria = CKEditor5Field(blank=True, config_name='default')
    atribuicoes_profissionais = CKEditor5Field(blank=True, config_name='default')
    material_didatico = CKEditor5Field(blank=True, config_name='default')
    ferramentas_comunicacao = CKEditor5Field(blank=True, config_name='default')
    carga_horaria_presencial_acompanhamento = CKEditor5Field(blank=True, config_name='default')
    armazenamento_gerenciamento_dados = CKEditor5Field(blank=True, config_name='default')

    history = HistoricalRecords()

    def __str__(self):
        return f"Dinâmica EAD - {self.ppc.curso.nome}" 

class ComponenteCurricular(models.Model):
    TIPO_CHOICES = [
        ("disciplina", "Disciplina"),
        ("modulo", "Módulo"),
        ("seminario", "Seminário de Integração"),
        ("atividade", "Atividade Orientada"),
    ]
    NATUREZA_CHOICES = [
        ("obrigatoria", "Obrigatória"),
        ("optativa", "Optativa"),
    ]
    NUCLEO_CHOICES = [
        ("NC", "Núcleo Comum"),
        ("NE", "Núcleo Específico"),
        ("NL", "Núcleo Livre"),
        ("AC", "Atividade Complementar"),
        ("ACEx", "Atividade Curricular de Extensão"),
    ]
    ppc = models.ForeignKey(
        PPC,
        on_delete=models.CASCADE,
        related_name="componentes_curriculares"
    )
    nome = models.CharField(max_length=200)
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES)
    natureza = models.CharField(max_length=20, choices=NATUREZA_CHOICES)
    nucleo = models.CharField(max_length=4, choices=NUCLEO_CHOICES)
    periodo = models.PositiveSmallIntegerField()
    carga_horaria_teorica = models.PositiveIntegerField()
    carga_horaria_pratica = models.PositiveIntegerField()
    carga_horaria_pcc = models.PositiveIntegerField(default=0, help_text="Horas de Prática como Componente Curricular (só licenciaturas)")
    unidade_academica_componente = models.CharField(max_length=200)
    ementa = models.TextField()

    history = HistoricalRecords()

    def __str__(self):
            return f"Componente Curricular - {self.ppc.curso.nome}"

class Bibliografia(models.Model):
    TIPO_CHOICES = [("basica", "Básica"), ("complementar", "Complementar")]
    componente = models.ForeignKey(ComponenteCurricular, on_delete=models.CASCADE, related_name="bibliografias")
    tipo = models.CharField(max_length=15, choices=TIPO_CHOICES)
    titulo = models.CharField(max_length=300)
    autores = models.CharField(max_length=300)
    editora = models.CharField(max_length=150, blank=True)
    cidade = models.CharField(max_length=100, blank=True)
    ano = models.PositiveIntegerField(blank=True, null=True)

    def __str__(self):
        return self.titulo
class Apendice(models.Model):
    TIPO_CHOICES = [
        ("corpo_docente","Relação do corpo docente e titulação"),
        ("quadro_oferta","Quadro semestral de oferta de componentes curriculares"),
    ]

    ppc = models.ForeignKey(PPC,on_delete=models.CASCADE,related_name="apendices")
    tipo = models.CharField(max_length=30,choices=TIPO_CHOICES)
    titulo = models.CharField(max_length=200)
    descricao = CKEditor5Field(blank=True, config_name='default')
    arquivo = models.FileField(upload_to="apendices/",blank=True)

    history = HistoricalRecords()

    def __str__(self):
        return self.titulo

class RelacaoComponente(models.Model):
    TIPO_CHOICES = [
        ("pre_requisito", "Pré-requisito"),
        ("co_requisito", "Co-requisito"),
        ("equivalente", "Equivalente"),
    ]
    componente = models.ForeignKey(
        ComponenteCurricular,
        on_delete=models.CASCADE,
        related_name="relacoes"
    )
    componente_relacionado = models.ForeignKey(
        ComponenteCurricular,
        on_delete=models.CASCADE,
        related_name="relacionado_em"
    )
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES)

    class Meta:
        unique_together = ('componente', 'componente_relacionado', 'tipo')

    history = HistoricalRecords()

    def __str__(self):
        return f"{self.componente.nome} → {self.get_tipo_display()} → {self.componente_relacionado.nome}"

