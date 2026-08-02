# ppc/models.py
from django.db import models


class Curso(models.Model):
    nome = models.CharField(max_length=200)
    unidade_academica = models.CharField(max_length=200)
    area_conhecimento = models.CharField(max_length=200)  # áreas CAPES

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

    # -- Campos condicionais (só para EAD) --
    publico_alvo_ead = models.TextField(blank=True)
    ato_integracao_uab = models.CharField(max_length=200, blank=True)
    ato_credenciamento_mec = models.CharField(max_length=200, blank=True)
    polos_ead = models.TextField(blank=True)

    # -- Apresentação (texto narrativo) --
    apresentacao_texto = models.TextField()

    # -- Exposição de Motivos --
    tipo_ppc = models.CharField(max_length=20, choices=TIPO_PPC_CHOICES)
    exposicao_motivos = models.TextField()

    # -- Objetivos --
    objetivo_geral = models.TextField()
    objetivo_especifico = models.TextField()

    # -- Princípios Norteadores para a Formação Profissional --
    principios_geral = models.TextField()
    principios_pratica_profissional = models.TextField()
    principios_formacao_tecnica = models.TextField()
    principios_formacao_etica_social = models.TextField()
    principios_interdisciplinaridade = models.TextField()
    principios_articulacao_teoria_pratica = models.TextField()

    # -- Expectativas da Formação Profissional --
    perfil_curso = models.TextField()
    perfil_habilidades = models.TextField()

    # -- Trabalho de Conclusão de Curso --
    tcc = models.TextField()

    # -- Detalhes sobre Política e Gestão do Estágio Obrigátorio e Não Obrigátorio
    estagio = models.TextField()

    # -- Atividades Complementares do Curso --
    atividades_complementares = models.TextField()

    # -- Integração de Ensino, Pesquisa e Extensão --
    politicas_integrada = models.TextField()

    # -- Avaliação de Processo de Ensino e Aprendizagem --
    avaliacao_ensino_aprendigem = models.TextField()

    # -- Avaliação do Projeto de Curso -- 
    avaliacao_projeto_curso = models.TextField()

    # -- Qualificação de docentes e técnico-administrativos --
    qualificacao = models.TextField()

    # -- Requisitos legais e Normativos Obrigátorios --
    diretrizes_curriculares_nacionais_curso = models.TextField()  
    diretrizes_curriculares_nacionais_educacao_basica = models.TextField(blank=True)
    diretrizes_etnico_raciais_historia_cultura_afro_indigena = models.TextField()
    diretrizes_educacao_direitos_humanos = models.TextField()
    protecao_direitos_pessoa_transtorno_espectro_autista = models.TextField()
    componente_curricular_libras = models.TextField()
    politicas_educacao_ambiental = models.TextField()
    diretrizes_formacao_professores_educacao_basica = models.TextField(blank=True)
    condicoes_acesso_pessoas_deficiencia_mobilidade_reduzida = models.TextField()

    # -- Biblografias do PPC --
    bibliografias_ppc = models.TextField()

    # -- Estrutura Curricular --
    estrutura_curricular_descricao = models.TextField()
    estrutura_curricular_informacoes_complementares = models.TextField()

    def __str__(self):
        return f"PPC - {self.curso.nome}"
    
class DinamicaEAD(models.Model):
    ppc = models.OneToOneField(PPC,on_delete=models.CASCADE,related_name="dinamica_ead")

    dinamica_atividades_presenciais_distancia = models.TextField(blank=True)
    recuperacao_estudos_permanencia = models.TextField(blank=True)
    componente_informatica_basica = models.TextField(blank=True)
    atuacao_tutoria = models.TextField(blank=True)
    atribuicoes_profissionais = models.TextField(blank=True)
    material_didatico = models.TextField(blank=True)
    ferramentas_comunicacao = models.TextField(blank=True)
    carga_horaria_presencial_acompanhamento = models.TextField(blank=True)
    armazenamento_gerenciamento_dados = models.TextField(blank=True)

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
    descricao = models.TextField(blank=True)
    arquivo = models.FileField(upload_to="apendices/",blank=True)

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

    def __str__(self):
        return f"{self.componente.nome} → {self.get_tipo_display()} → {self.componente_relacionado.nome}"

