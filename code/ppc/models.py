# ppc/models.py
from django.db import models
from django_ckeditor_5.fields import CKEditor5Field
from django.utils import timezone
from simple_history.models import HistoricalRecords
from django.core.exceptions import ValidationError
from django.conf import settings


class CineBrasilCurso(models.Model):
    nome_curso = models.CharField(max_length=255, verbose_name='Nome do curso')
    area_geral_codigo = models.CharField(max_length=2, verbose_name='Código da área geral')
    area_geral_nome = models.CharField(max_length=255, verbose_name='Nome da área geral')

    rotulo_codigo = models.CharField(max_length=8, verbose_name='Código do rótulo')
    rotulo_nome = models.CharField(max_length=255, verbose_name='Nome do rótulo')

    origem = models.CharField(
        max_length=10,
        choices=[
            ("DCN", "DCN"),
            ("CNCST", "CNCST"),
        ],
        blank=True,
        verbose_name='Origem',
    )
class Curso(models.Model):
    nome = models.CharField(max_length=200, verbose_name='Nome')
    cine_brasil = models.ForeignKey(
        CineBrasilCurso,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name='Cine Brasil',
    )
    unidade_academica = models.CharField(max_length=200, verbose_name='Unidade acadêmica')
    area_conhecimento = models.CharField(max_length=200, verbose_name='Área de conhecimento')  # áreas CAPES
    carga_horaria_minima = models.PositiveIntegerField(null=True, blank=True, verbose_name='Carga horária mínima')
    carga_horaria_maxima = models.PositiveIntegerField(null=True, blank=True, verbose_name='Carga horária máxima')

    class Meta:
        verbose_name = "Curso"
        verbose_name_plural = "Cursos"

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
        ('semipresencial', 'Semipresencial'),
    ]
    GRAU_CHOICES = [
        ('bacharelado', 'Bacharelado'),
        ('licenciatura', 'Licenciatura'),
        ('tecnologo', 'Tecnólogo',)
    ]
    STATUS_CHOICES = [
        ('rascunho', 'Rascunho'),
        ('em_revisao', 'Em Revisão'),
        ('aprovado', 'Aprovado'),
    ]
    SEMESTRE_CHOICES = [
        (1, '1'),
        (2, '2'),
    ]

    curso = models.ForeignKey(Curso, on_delete=models.CASCADE, related_name='ppcs', verbose_name='Curso')
    ppc_anterior = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.PROTECT,
        related_name='edicoes', verbose_name='PPC anterior',
    )

    # -- Informações Gerais --
    modalidade = models.CharField(max_length=20, choices=MODALIDADE_CHOICES, verbose_name='Modalidade')
    grau_academico = models.CharField(max_length=20, choices=GRAU_CHOICES, verbose_name='Grau acadêmico')
    turno_funcionamento = models.CharField(max_length=50, verbose_name='Turno de funcionamento')
    carga_horaria_total = models.PositiveIntegerField(help_text="em horas", blank=True, null=True, default=0, verbose_name='Carga horária total')
    numero_vagas_anuais = models.PositiveIntegerField(verbose_name='Número de vagas anuais')
    duracao_minima_semestres = models.PositiveIntegerField(verbose_name='Duração mínima (semestres)')
    duracao_media_semestres = models.PositiveIntegerField(verbose_name='Duração média (semestres)')
    duracao_maxima_semestres = models.PositiveIntegerField(verbose_name='Duração máxima (semestres)')
    diretor = models.CharField(max_length=200, verbose_name='Diretor')
    vice_diretor = models.CharField(max_length=200, verbose_name='Vice-diretor')
    coordenador_curso = models.CharField(max_length=200, verbose_name='Coordenador do curso')
    vice_coordenador_curso = models.CharField(max_length=200, verbose_name='Vice-coordenador do curso')
    reitor = models.CharField(max_length=200, blank=True, verbose_name='Reitor')
    vice_reitor = models.CharField(max_length=200, blank=True, verbose_name='Vice-reitor')
    coordenador_administrativo = models.CharField(max_length=200, blank=True, verbose_name='Coordenador administrativo')

    # -- Datas --
    criado_em = models.DateTimeField(auto_now_add=True, verbose_name='Criado em')
    atualizado_em = models.DateTimeField(auto_now=True, verbose_name='Atualizado em')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='rascunho', verbose_name='Status')
    numero_resolucao = models.CharField(max_length=100, blank=True, verbose_name="Número da Resolução de Aprovação (Pode ficar em branco durante o processo de produção)")
    numero_processo_eletronico = models.CharField(max_length=100, blank=True, verbose_name="Número do processo eletrônico")
    data_aprovacao = models.DateField(null=True, blank=True, verbose_name='Data de aprovação')
    data_resolucao = models.DateField(null=True, blank=True, verbose_name='Data da resolução')
    ano_vigencia = models.PositiveIntegerField(null=True, blank=True, verbose_name='Ano de vigência')
    semestre_vigencia = models.PositiveSmallIntegerField(choices=SEMESTRE_CHOICES, default=1, verbose_name='Semestre de vigência')

    @property
    def periodo_vigencia(self):
        return f"{self.ano_vigencia}/{self.semestre_vigencia}"

    def clean(self):
        super().clean()
        self._validar_transicao_duracoes()

    def _validar_transicao_duracoes(self, campos_salvos=None):
        campos = {"status", "duracao_minima_semestres", "duracao_media_semestres", "duracao_maxima_semestres"}
        if campos_salvos is not None and not (campos & set(campos_salvos)):
            return
        anterior = type(self).objects.filter(pk=self.pk).values(
            *campos
        ).first() if self.pk else None
        if anterior:
            alterados = {campo for campo in campos if getattr(self, campo) != anterior[campo]}
            if campos_salvos is not None:
                alterados &= set(campos_salvos)
            if not alterados:
                return
            status_original = anterior["status"]
            maximo_original = anterior["duracao_maxima_semestres"]
        else:
            alterados = {"status", "duracao_minima_semestres", "duracao_media_semestres", "duracao_maxima_semestres"}
            status_original = "rascunho"
            maximo_original = None
            if self.status == "rascunho":
                return
        from .services.regras_matriz import validar_status_e_duracoes
        validar_status_e_duracoes(
            self, status_original=status_original, maximo_original=maximo_original,
            validar_duracoes=bool(alterados & {"duracao_minima_semestres", "duracao_media_semestres", "duracao_maxima_semestres", "status"}),
        )

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        self._validar_transicao_duracoes(update_fields)
        if self.ppc_anterior_id:
            if self.ppc_anterior_id == self.pk:
                raise ValidationError({"ppc_anterior": "Um PPC não pode ser anterior a si mesmo."})
            curso_anterior = type(self).objects.filter(pk=self.ppc_anterior_id).values_list("curso_id", flat=True).first()
            if curso_anterior != self.curso_id:
                raise ValidationError({"ppc_anterior": "O PPC anterior deve pertencer ao mesmo curso."})
            visitados = {self.pk} if self.pk else set()
            cursor_id = self.ppc_anterior_id
            while cursor_id:
                if cursor_id in visitados:
                    raise ValidationError({"ppc_anterior": "A cadeia de PPCs não pode formar um ciclo."})
                visitados.add(cursor_id)
                cursor_id = type(self).objects.filter(pk=cursor_id).values_list("ppc_anterior_id", flat=True).first()
        super().save(*args, **kwargs)

    # -- Campos condicionais (só para EAD) --
    publico_alvo_ead = CKEditor5Field(blank=True, config_name='default', verbose_name='Público-alvo EAD')
    ato_integracao_uab = CKEditor5Field(blank=True, config_name='default', verbose_name='Ato de integração UAB')
    ato_credenciamento_mec = CKEditor5Field(blank=True, config_name='default', verbose_name='Ato de credenciamento MEC')
    polos_ead = CKEditor5Field(blank=True, config_name='default', verbose_name='Polos EAD')

    # -- Apresentação (texto narrativo) --
    apresentacao_texto = CKEditor5Field(blank=True, config_name='default', verbose_name='Apresentação')

    # -- Exposição de Motivos --
    tipo_ppc = models.CharField(max_length=20, choices=TIPO_PPC_CHOICES, verbose_name="Tipo de PPC")
    exposicao_motivos = CKEditor5Field(blank=True, config_name='default', verbose_name="Exposição de Motivos")

    # -- Objetivos --
    objetivo_geral = CKEditor5Field(blank=True, config_name='default', verbose_name='Objetivo geral')
    objetivo_especifico = CKEditor5Field(blank=True, config_name='default', verbose_name='Objetivos específicos')

    # -- Princípios Norteadores para a Formação Profissional --
    principios_geral = CKEditor5Field(blank=True, config_name='default', verbose_name="Princípios Gerais")
    principios_pratica_profissional = CKEditor5Field(blank=True, config_name='default', verbose_name="Prática Profissional")
    principios_formacao_tecnica = CKEditor5Field(blank=True, config_name='default', verbose_name="Formação Técnica")
    principios_formacao_etica_social = CKEditor5Field(blank=True, config_name='default', verbose_name="Formação Ética e Função Social do Profissional")
    principios_interdisciplinaridade = CKEditor5Field(blank=True, config_name='default', verbose_name="Interdisciplinaridade")
    principios_articulacao_teoria_pratica = CKEditor5Field(blank=True, config_name='default', verbose_name="Articulação entre Teoria e Prática")

    # -- Expectativas da Formação Profissional --
    perfil_curso = CKEditor5Field(blank=True, config_name='default', verbose_name="Perfil do Curso")
    perfil_habilidades = CKEditor5Field(blank=True, config_name='default', verbose_name="Perfil e Habilidades do Egresso")

    # -- Trabalho de Conclusão de Curso --
    tcc = CKEditor5Field(blank=True, config_name='default', verbose_name='Trabalho de conclusão de curso (TCC)')

    # -- Detalhes sobre Política e Gestão do Estágio Obrigatório e Não Obrigatório --
    estagio = CKEditor5Field(blank=True, config_name='default', verbose_name="Política e Gestão de Estágio Curricular Obrigatório e Não Obrigatório")

    # -- Atividades Complementares do Curso --
    atividades_complementares = CKEditor5Field(blank=True, config_name='default', verbose_name="Atividades Complementares")

    # -- Integração de Ensino, Pesquisa e Extensão --
    politicas_integrada = CKEditor5Field(blank=True, config_name='default', verbose_name="Integração Ensino, Pesquisa e Extensão")

    # -- Avaliação do Processo de Ensino e Aprendizagem --
    avaliacao_ensino_aprendizagem = CKEditor5Field(blank=True, config_name='default', verbose_name="Avaliação do Processo de Ensino e de Aprendizagem")

    # -- Avaliação do Projeto de Curso --
    avaliacao_projeto_curso = CKEditor5Field(blank=True, config_name='default', verbose_name="Avaliação do Projeto de Curso")

    # -- Qualificação de docentes e técnico-administrativos --
    qualificacao = CKEditor5Field(blank=True, config_name='default', verbose_name="Qualificação de Docentes e Técnico-Administrativos")    

    # -- Requisitos legais e Normativos Obrigátorios --
    diretrizes_curriculares_nacionais_curso = CKEditor5Field(blank=True, config_name='default', verbose_name="Diretrizes Curriculares Nacionais do Curso")  
    diretrizes_curriculares_nacionais_educacao_basica = CKEditor5Field(blank=True, config_name='default', verbose_name="Diretrizes Curriculares Nacionais da Educação Básica")
    diretrizes_etnico_raciais_historia_cultura_afro_indigena = CKEditor5Field(blank=True, config_name='default', verbose_name="Diretrizes para Educação das Relações Étnico-Raciais e Ensino de História e Cultura Afro-Brasileira e Indígena")
    diretrizes_educacao_direitos_humanos = CKEditor5Field(blank=True, config_name='default', verbose_name="Diretrizes Nacionais para a Educação em Direitos Humanos")
    protecao_direitos_pessoa_transtorno_espectro_autista = CKEditor5Field(blank=True, config_name='default', verbose_name="Proteção dos Direitos da Pessoa com Transtorno do Espectro Autista")
    componente_curricular_libras = CKEditor5Field(blank=True, config_name='default', verbose_name="Componente Curricular de Libras")
    politicas_educacao_ambiental = CKEditor5Field(blank=True, config_name='default', verbose_name="Políticas de Educação Ambiental")
    diretrizes_formacao_professores_educacao_basica = CKEditor5Field(blank=True, config_name='default', verbose_name="Diretrizes Curriculares Nacionais para a Formação de Professores da Educação Básica")
    condicoes_acesso_pessoas_deficiencia_mobilidade_reduzida = CKEditor5Field(blank=True, config_name='default', verbose_name="Condições de Acesso para Pessoas com Deficiência e/ou Mobilidade Reduzida")

    # -- Bibliografias do PPC --
    bibliografias_ppc = CKEditor5Field(blank=True, config_name='default', verbose_name="Referências")

    # -- Estrutura Curricular --
    estrutura_curricular_descricao = CKEditor5Field(blank=True, config_name='default', verbose_name="Descrição Geral")
    estrutura_curricular_informacoes_complementares = CKEditor5Field(blank=True, config_name='default', verbose_name="Informações Complementares")
    history = HistoricalRecords()

    class Meta:
        verbose_name = "PPC"
        verbose_name_plural = "PPCs"

    def __str__(self):
        return f"PPC - {self.curso.nome}"
    
class DinamicaEAD(models.Model):
    ppc = models.OneToOneField(PPC,on_delete=models.CASCADE,related_name="dinamica_ead", verbose_name='PPC')

    dinamica_atividades_presenciais_distancia = CKEditor5Field(blank=True, config_name='default', verbose_name='Dinâmica das atividades presenciais e a distância')
    recuperacao_estudos_permanencia = CKEditor5Field(blank=True, config_name='default', verbose_name='Recuperação de estudos e permanência')
    componente_informatica_basica = CKEditor5Field(blank=True, config_name='default', verbose_name='Componente de informática básica')
    atuacao_tutoria = CKEditor5Field(blank=True, config_name='default', verbose_name='Atuação da tutoria')
    atribuicoes_profissionais = CKEditor5Field(blank=True, config_name='default', verbose_name='Atribuições profissionais')
    material_didatico = CKEditor5Field(blank=True, config_name='default', verbose_name='Material didático')
    ferramentas_comunicacao = CKEditor5Field(blank=True, config_name='default', verbose_name='Ferramentas de comunicação')
    carga_horaria_presencial_acompanhamento = CKEditor5Field(blank=True, config_name='default', verbose_name='Carga horária presencial de acompanhamento')
    armazenamento_gerenciamento_dados = CKEditor5Field(blank=True, config_name='default', verbose_name='Armazenamento e gerenciamento de dados')

    history = HistoricalRecords()

    def __str__(self):
        return f"Dinâmica EAD - {self.ppc.curso.nome}" 

class ComponenteCurricular(models.Model):
    """Catálogo compartilhado. Só o que é intrínseco ao componente, não muda por PPC."""
    TIPO_CHOICES = [
        ("disciplina", "Disciplina"),
        ("modulo", "Módulo"),
        ("seminario", "Seminário de Integração"),
        ("atividade", "Atividade Orientada"),
    ]
    CCU_CHOICES = [
        (True, 'Sim'),
        (None, 'Não sei'),
        (False, 'Não'),
    ]
    
    STATUS_CHOICES = [
        ("pendente", "Pendente de aprovação"),
        ("aprovado", "Aprovado"),
    ]

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='aprovado', verbose_name='Status')

    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='componentes_criados',
        verbose_name='Criado por',
    )

    codigo = models.CharField(max_length=20, blank=True, verbose_name='Código')
    nome = models.CharField(max_length=200, verbose_name='Nome')
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, verbose_name='Tipo')
    ccu = models.BooleanField(null=True, blank=True, choices=CCU_CHOICES, verbose_name='Esse componente é uma CCU?')
    
    carga_horaria_teorica = models.PositiveIntegerField(verbose_name='Carga horária teórica')
    carga_horaria_pratica = models.PositiveIntegerField(verbose_name='Carga horária prática')
    unidade_academica_componente = models.CharField(max_length=200, blank=True, verbose_name='Unidade acadêmica do componente')
    ementa = models.TextField(verbose_name='Ementa')

    carga_horaria_estudante = models.PositiveIntegerField(null=True, blank=True, verbose_name='Carga horária do estudante')
    carga_horaria_professor = models.PositiveIntegerField(null=True, blank=True, verbose_name='Carga horária do professor')
    carga_horaria_acex = models.PositiveIntegerField(null=True, blank=True, verbose_name='Carga horária ACEx')

    def clean(self):
        super().clean()

        if (
            self.tipo == 'atividade'
            and self.carga_horaria_professor is not None
            and self.carga_horaria_estudante is not None
            and self.carga_horaria_professor > self.carga_horaria_estudante
        ):
            raise ValidationError({
                'carga_horaria_professor': "A carga horária do professor não pode ser maior que a do estudante."
            })

        total = self.carga_horaria_computada_total
        if total % 8 != 0:
            campo = 'carga_horaria_estudante' if self.tipo == 'atividade' else 'carga_horaria_teorica'
            raise ValidationError({
                campo: f"A carga horária total do componente ({total}h) deve ser múltipla de 8."
            })

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        if update_fields is None or "codigo" in update_fields:
            from ppc.services.codigos_componentes import validar_codigo_componente
            validar_codigo_componente(self.codigo, self)
        super().save(*args, **kwargs)

    @property
    def carga_horaria_computada_total(self):
        acex = self.carga_horaria_acex if self.carga_horaria_acex != None else 0
        if self.tipo == 'atividade':
            return (self.carga_horaria_estudante + acex) or 0
        return self.carga_horaria_teorica + self.carga_horaria_pratica + acex

    history = HistoricalRecords()

    def __str__(self):
        return f"{self.nome} ({self.codigo})" if self.codigo else self.nome


class ComponenteNaMatriz(models.Model):
    """O vínculo: este componente está na matriz deste PPC, neste período, com esta natureza."""
    NATUREZA_CHOICES = [
        ("obrigatoria", "Obrigatória"),
        ("optativa", "Optativa"),
    ]
    NUCLEO_CHOICES = [
        ("NC", "Núcleo Comum"),
        ("NE", "Núcleo Específico"),
    ]
    nucleo = models.CharField(max_length=4, choices=NUCLEO_CHOICES, default='NE', verbose_name='Núcleo')

    GRUPO_LICENCIATURA_CHOICES = [
        (1, "Grupo 1"),
        (2, "Grupo 2"),
        (4, "Grupo 4 (Estágio)"),
    ]
    grupo_licenciatura = models.PositiveSmallIntegerField(
        null=True, blank=True,
        choices=GRUPO_LICENCIATURA_CHOICES,
        verbose_name="Grupo (licenciatura)",
    )

    def clean(self):
            super().clean()
            if self.nucleo == "NC" and self.natureza != "obrigatoria":
                raise ValidationError({
                    "natureza": "Componentes do Núcleo Comum são sempre de natureza obrigatória."
                })
            if self.ppc_id and self.periodo is not None:
                from .services.regras_matriz import validar_periodo_ppc, validar_mudanca_periodo
                if self.pk:
                    anterior = type(self).objects.filter(pk=self.pk).values_list("periodo", flat=True).first()
                    if anterior is not None and anterior != self.periodo:
                        validar_periodo_ppc(self.ppc, self.periodo)
                        validar_mudanca_periodo(self, self.periodo, "ppc")
                else:
                    validar_periodo_ppc(self.ppc, self.periodo)
    ppc = models.ForeignKey(PPC, on_delete=models.CASCADE, related_name="matriz_componentes", verbose_name='PPC')
    componente = models.ForeignKey(ComponenteCurricular, on_delete=models.PROTECT, related_name="uso_em_ppcs", verbose_name='Componente')
    periodo = models.PositiveSmallIntegerField(verbose_name='Período')
    natureza = models.CharField(max_length=20, choices=NATUREZA_CHOICES, verbose_name='Natureza')

    class Meta:
        unique_together = ('ppc', 'componente')
    
    def save(self, *args, validar_limite_periodo=True, **kwargs):
        # Regra no servidor: fora de licenciatura o grupo nunca é gravado,
        # independentemente de qual view, import ou script criou o vínculo.
        if self.ppc_id and self.ppc.grau_academico != 'licenciatura':
            self.grupo_licenciatura = None
        if self.ppc_id:
            from .services.regras_matriz import validar_periodo_ppc, validar_mudanca_periodo
            if self.pk:
                anterior = type(self).objects.filter(pk=self.pk).values_list('periodo', flat=True).first()
                if anterior is not None and anterior != self.periodo:
                    if validar_limite_periodo:
                        validar_periodo_ppc(self.ppc, self.periodo)
                    validar_mudanca_periodo(self, self.periodo, 'ppc')
            else:
                if validar_limite_periodo:
                    validar_periodo_ppc(self.ppc, self.periodo)
        super().save(*args, **kwargs)

    history = HistoricalRecords()

    def __str__(self):
        return f"{self.componente.nome} — {self.ppc.curso.nome} (período {self.periodo})"


class Bibliografia(models.Model):
    TIPO_CHOICES = [("basica", "Básica"), ("complementar", "Complementar")]
    componente_na_matriz = models.ForeignKey(ComponenteNaMatriz, on_delete=models.CASCADE, related_name="bibliografias", verbose_name='Componente na matriz')
    referencia = models.ForeignKey(
        "ReferenciaBibliografica", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="bibliografias_ppc",
        verbose_name='Referência bibliográfica',
    )
    tipo = models.CharField(max_length=15, choices=TIPO_CHOICES, verbose_name='Tipo')
    titulo = models.CharField(max_length=300, verbose_name='Título')
    autores = models.CharField(max_length=300, verbose_name='Autores')
    editora = models.CharField(max_length=150, blank=True, verbose_name='Editora')
    cidade = models.CharField(max_length=100, blank=True, verbose_name='Cidade')
    ano = models.PositiveIntegerField(blank=True, null=True, verbose_name='Ano')

    class Meta:
        verbose_name = "Bibliografia"
        verbose_name_plural = "Bibliografias"
        constraints = [models.UniqueConstraint(
            fields=["componente_na_matriz", "referencia"],
            name="uniq_bibliografia_obra_por_componente",
        )]

    def save(self, *args, **kwargs):
        if self.pk:
            anterior = type(self).objects.filter(pk=self.pk).values(
                "componente_na_matriz_id", "referencia_id", "tipo", "titulo", "autores", "editora", "cidade", "ano"
            ).first()
            if anterior and anterior["referencia_id"] and any(anterior[campo] != getattr(self, campo) for campo in (
                "componente_na_matriz_id", "referencia_id", "tipo", "titulo", "autores", "editora", "cidade", "ano"
            )):
                raise ValidationError("Esta referência veio da Biblioteca e não pode ser editada. Remova-a e escolha outra obra.")
        super().save(*args, **kwargs)
    history = HistoricalRecords()

    def __str__(self):
        return self.titulo


class ReferenciaBibliografica(models.Model):
    """Catálogo institucional de referências bibliográficas da UFCAT — existe
    independente de estar vinculada a qualquer componente curricular ou PPC."""
    titulo = models.CharField(max_length=300, verbose_name='Título')
    autores = models.CharField(max_length=300, blank=True, verbose_name='Autores')
    editora = models.CharField(max_length=150, blank=True, verbose_name='Editora')
    cidade = models.CharField(max_length=100, blank=True, verbose_name='Cidade')
    ano = models.PositiveIntegerField(blank=True, null=True, verbose_name='Ano')
    criado_em = models.DateTimeField(auto_now_add=True, verbose_name='Criado em')
    history = HistoricalRecords()

    def __str__(self):
        return self.titulo

class RelacaoComponente(models.Model):
    TIPO_CHOICES = [
        ("pre_requisito", "Pré-requisito"),
        ("co_requisito", "Co-requisito"),
    ]
    componente_na_matriz = models.ForeignKey(ComponenteNaMatriz, on_delete=models.CASCADE, related_name="relacoes", verbose_name='Componente na matriz')
    componente_relacionado_na_matriz = models.ForeignKey(ComponenteNaMatriz, on_delete=models.CASCADE, related_name="relacionado_em", verbose_name='Componente relacionado na matriz')
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, verbose_name='Tipo')

    class Meta:
        unique_together = ('componente_na_matriz', 'componente_relacionado_na_matriz', 'tipo')

    def clean(self, validar_periodo=True):
        super().clean()
        if self.componente_na_matriz_id and self.componente_relacionado_na_matriz_id:
            if self.componente_na_matriz.ppc_id != self.componente_relacionado_na_matriz.ppc_id:
                raise ValidationError("Os dois componentes da relação precisam estar na mesma matriz (mesmo PPC).")
            if validar_periodo:
                from .services.regras_matriz import validar_relacao_periodo
                validar_relacao_periodo(self)

    def save(self, *args, validar_periodo=True, **kwargs):
        validar = not self.pk
        if self.pk:
            anterior = type(self).objects.filter(pk=self.pk).values(
                "componente_na_matriz_id", "componente_relacionado_na_matriz_id", "tipo"
            ).first()
            validar = anterior is None or any(anterior[campo] != getattr(self, campo) for campo in anterior)
        if validar:
            self.clean(validar_periodo=validar_periodo)
        super().save(*args, **kwargs)

    history = HistoricalRecords()

    def __str__(self):
        return f"{self.componente_na_matriz.componente.nome} → {self.get_tipo_display()} → {self.componente_relacionado_na_matriz.componente.nome}"




class Apendice(models.Model):
    TIPO_CHOICES = [
        ("corpo_docente","Relação do corpo docente e titulação"),
        ("quadro_oferta","Quadro semestral de oferta de componentes curriculares"),
        ("estagio","Estágio"),
        ("tcc","Trabalho de Conclusão de Curso"),
        ("ac","Atividade Complementar"),
    ]

    ppc = models.ForeignKey(PPC,on_delete=models.CASCADE,related_name="apendices", verbose_name='PPC')
    tipo = models.CharField(max_length=30,choices=TIPO_CHOICES, verbose_name='Tipo')
    titulo = models.CharField(max_length=200, verbose_name='Título')
    descricao = CKEditor5Field(blank=True, config_name='default', verbose_name='Descrição')
    arquivo = models.FileField(upload_to="apendices/",blank=True, verbose_name='Arquivo')

    history = HistoricalRecords()

    class Meta:
        verbose_name = "Apêndice"
        verbose_name_plural = "Apêndices"

    def __str__(self):
        return self.titulo


class MembroNDE(models.Model):
    TITULACAO_CHOICES = [
        ('doutor', 'Doutor(a)'),
        ('mestre', 'Mestre'),
        ('especialista', 'Especialista'),
        ('graduado', 'Graduado(a)'),
    ]
    REGIME_CHOICES = [
        ('de', 'Dedicação Exclusiva'),
        ('40h', '40 horas'),
        ('20h', '20 horas'),
    ]
    FUNCAO_CHOICES = [
        ('presidente', 'Presidente/Coordenador(a) do NDE'),
        ('membro', 'Membro'),
    ]

    curso = models.ForeignKey(Curso, on_delete=models.CASCADE, related_name='membros_nde', verbose_name="Curso")
    nome = models.CharField(max_length=200, verbose_name="Nome Completo")
    titulacao = models.CharField(max_length=20, choices=TITULACAO_CHOICES, verbose_name="Titulação")
    regime_trabalho = models.CharField(max_length=10, choices=REGIME_CHOICES, verbose_name="Regime de Trabalho")
    funcao = models.CharField(max_length=20, choices=FUNCAO_CHOICES, default='membro', verbose_name="Função no Núcleo")
    portaria_designacao = models.CharField(max_length=200, blank=True, verbose_name="Portaria/Ato de Designação")
    data_inicio = models.DateField(verbose_name="Data de Início no Núcleo")
    data_fim = models.DateField(blank=True, null=True, verbose_name="Data de Saída (se aplicável)")
    ativo = models.BooleanField(default=True, verbose_name="Ativo no Núcleo")

    class Meta:
        verbose_name = "Membro do NDE"
        verbose_name_plural = "Membros do NDE"

    history = HistoricalRecords()

    def __str__(self):
        return f"{self.nome} ({self.curso.nome})"




class MatrizReferenciaCurricular(models.Model):
    GRAU_CHOICES = PPC.GRAU_CHOICES
    matriz_anterior = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT,
        related_name="edicoes", verbose_name="Matriz anterior",
    )
    curso = models.ForeignKey(
        Curso,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="matrizes_referencia",
        help_text="Pode ficar em branco até alguém identificar a que curso esta matriz pertence.",
        verbose_name='Curso',
    )
    identificador_origem = models.CharField(
        max_length=50,
        unique=True,
        null=True,
        blank=True,
        default=None,
        help_text="Identificador original da planilha (ex: 'FIS-LN-2C'), para rastreio antes/depois de vincular a um Curso.",
        verbose_name='Identificador de origem',
    )
    nome = models.CharField(max_length=200, blank=True, verbose_name='Nome')
    grau_academico = models.CharField(
        max_length=20, choices=GRAU_CHOICES, null=True, blank=True,
        verbose_name="Grau acadêmico da matriz",
    )
    STATUS_APROVADA = "aprovada"
    STATUS_EM_MUDANCA = "em_mudanca"
    STATUS_CHOICES = [
        (STATUS_APROVADA, "Aprovada"),
        (STATUS_EM_MUDANCA, "Em mudança"),
    ]
    status = models.CharField(
        "Estado", max_length=12, choices=STATUS_CHOICES, default=STATUS_APROVADA
    )

    numero_periodos = models.PositiveSmallIntegerField(
        default=8,
        help_text="Quantidade de períodos exibidos na tela de edição desta matriz.",
        verbose_name='Número de períodos',
    )

    criado_em = models.DateTimeField(auto_now_add=True, verbose_name='Criado em')
    atualizado_em = models.DateTimeField(auto_now=True, verbose_name='Atualizado em')

    history = HistoricalRecords()

    def save(self, *args, **kwargs):
        if self.matriz_anterior_id:
            if not self.curso_id:
                raise ValidationError({"matriz_anterior": "Vincule a matriz a um curso antes de definir sua matriz anterior."})
            curso_anterior = type(self).objects.filter(pk=self.matriz_anterior_id).values_list("curso_id", flat=True).first()
            if curso_anterior is None or curso_anterior != self.curso_id:
                raise ValidationError({"matriz_anterior": "A matriz anterior deve pertencer ao mesmo curso."})
            visitados = {self.pk} if self.pk else set()
            cursor_id = self.matriz_anterior_id
            while cursor_id:
                if cursor_id in visitados:
                    raise ValidationError({"matriz_anterior": "A cadeia de edições não pode formar um ciclo."})
                visitados.add(cursor_id)
                cursor_id = type(self).objects.filter(pk=cursor_id).values_list("matriz_anterior_id", flat=True).first()
        super().save(*args, **kwargs)

    def __str__(self):
        if self.curso:
            return self.nome or f"Matriz de Referência — {self.curso.nome}"
        return f"Matriz sem curso vinculado ({self.identificador_origem})"


class ComponenteNaMatrizReferencia(models.Model):
    """Vínculo: este componente está nesta matriz de referência, neste período, com esta natureza.
    Mesmo papel que ComponenteNaMatriz cumpre para PPC, mas em nível institucional."""
    NATUREZA_CHOICES = [
        ("obrigatoria", "Obrigatória"),
        ("optativa", "Optativa"),
    ]
    NUCLEO_CHOICES = [
        ("NC", "Núcleo Comum"),
        ("NE", "Núcleo Específico"),
    ]
    nucleo = models.CharField(max_length=4, choices=NUCLEO_CHOICES, default='NE', verbose_name='Núcleo')

    GRUPO_LICENCIATURA_CHOICES = [
            (1, "Grupo 1"),
            (2, "Grupo 2"),
            (4, "Grupo 4 (Estágio)"),
        ]
    grupo_licenciatura = models.PositiveSmallIntegerField(
        null=True, blank=True,
        choices=GRUPO_LICENCIATURA_CHOICES,
        verbose_name="Grupo (licenciatura)",
    )

    def clean(self):
        super().clean()
        if self.nucleo == "NC" and self.natureza != "obrigatoria":
            raise ValidationError({
                "natureza": "Componentes do Núcleo Comum são sempre de natureza obrigatória."
            })
        if self.periodo is None or self.periodo < 1:
            raise ValidationError({"periodo": "O período deve ser maior que zero."})
        if self.pk:
            from .services.regras_matriz import validar_mudanca_periodo
            anterior = type(self).objects.filter(pk=self.pk).values_list("periodo", flat=True).first()
            if anterior is not None and anterior != self.periodo:
                validar_mudanca_periodo(self, self.periodo, "referencia")

    matriz = models.ForeignKey(
        MatrizReferenciaCurricular,
        on_delete=models.CASCADE,
        related_name="componentes",
        verbose_name='Matriz de referência',
    )
    componente = models.ForeignKey(
        ComponenteCurricular,
        on_delete=models.PROTECT,
        related_name="uso_em_matrizes_referencia",
        verbose_name='Componente',
    )
    periodo = models.PositiveSmallIntegerField(verbose_name='Período')
    natureza = models.CharField(max_length=20, choices=NATUREZA_CHOICES, verbose_name='Natureza')
    ordem = models.PositiveIntegerField(
        default=0,
        help_text="Posição dentro do período, para uso futuro no drag-and-drop.",
        verbose_name='Ordem',
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["matriz", "componente"],
                name="uniq_componente_matriz_referencia",
            )
        ]
        ordering = ["periodo", "ordem"]

    def save(self, *args, **kwargs):
        if self.matriz_id and self.matriz.grau_academico != "licenciatura":
            self.grupo_licenciatura = None
            if kwargs.get("update_fields") is not None:
                kwargs["update_fields"] = set(kwargs["update_fields"]) | {"grupo_licenciatura"}
        if self.periodo is None or self.periodo < 1:
            raise ValidationError({"periodo": "O período deve ser maior que zero."})
        if self.pk:
            from .services.regras_matriz import validar_mudanca_periodo
            anterior = type(self).objects.filter(pk=self.pk).values_list('periodo', flat=True).first()
            if anterior is not None and anterior != self.periodo:
                validar_mudanca_periodo(self, self.periodo, 'referencia')
        super().save(*args, **kwargs)

    history = HistoricalRecords()

    def __str__(self):
        return f"{self.componente.nome} — {self.matriz} (período {self.periodo})"


class RelacaoComponenteReferencia(models.Model):
    """Pré/co-requisito entre componentes de uma mesma matriz de referência.
    Mesmo papel de RelacaoComponente, em nível institucional."""
    TIPO_CHOICES = [
        ("pre_requisito", "Pré-requisito"),
        ("co_requisito", "Co-requisito"),
    ]
    item = models.ForeignKey(
        ComponenteNaMatrizReferencia, on_delete=models.CASCADE, related_name="relacoes",
        verbose_name='Componente',
    )
    item_relacionado = models.ForeignKey(
        ComponenteNaMatrizReferencia, on_delete=models.CASCADE, related_name="relacionado_em",
        verbose_name='Tem como pré/co-requisito',
    )
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, verbose_name='Tipo')

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['item', 'item_relacionado', 'tipo'],
                name='uniq_relacao_referencia',
            ),
        ]

    def clean(self, validar_periodo=True):
        super().clean()
        if self.item_id and self.item_relacionado_id:
            if self.item_id == self.item_relacionado_id:
                raise ValidationError("Um componente não pode se relacionar consigo mesmo.")
            if self.item.matriz_id != self.item_relacionado.matriz_id:
                raise ValidationError("Os dois componentes precisam estar na mesma matriz de referência.")
            if validar_periodo:
                from .services.regras_matriz import validar_relacao_periodo
                validar_relacao_periodo(self)

    def save(self, *args, validar_periodo=True, **kwargs):
        validar = not self.pk
        if self.pk:
            anterior = type(self).objects.filter(pk=self.pk).values("item_id", "item_relacionado_id", "tipo").first()
            validar = anterior is None or any(anterior[campo] != getattr(self, campo) for campo in anterior)
        if validar:
            self.clean(validar_periodo=validar_periodo)
        super().save(*args, **kwargs)

    history = HistoricalRecords()

    def __str__(self):
        return f"{self.item.componente.nome} → {self.get_tipo_display()} → {self.item_relacionado.componente.nome}"
class MapeamentoImportacaoMatriz(models.Model):
    """De-para entre o identificador de matriz na planilha da UFCAT e o Curso/matriz
    de referência do sistema. Preenchido manualmente antes de importar."""
    identificador_origem = models.CharField(
        max_length=50,
        unique=True,
        help_text="Ex: 'FIS-LN-2C', como aparece na coluna matriz_curricular da planilha.",
        verbose_name='Identificador de origem',
    )
    curso = models.ForeignKey(
        Curso,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        help_text="Deixe em branco até identificar a que curso este identificador pertence.",
        verbose_name='Curso',
    )
    nome_matriz_referencia = models.CharField(
        max_length=200,
        blank=True,
        help_text="Nome a dar à MatrizReferenciaCurricular criada (ex: 'Noturno'). Opcional.",
        verbose_name='Nome da matriz de referência',
    )
    observacao = models.CharField(max_length=300, blank=True, verbose_name='Observação')

    def __str__(self):
        return f"{self.identificador_origem} → {self.curso.nome}"


class ImportacaoPendencia(models.Model):
    """Guarda linhas da planilha que precisam de revisão manual antes/depois do
    import: ambíguas, duplicadas conflitantes, ou sem mapeamento de curso.
    Não é dado oficial — é fila de trabalho de quem está conduzindo o import."""

    TIPO_CHOICES = [
        ("ambigua", "Ambígua (núcleo/natureza indeterminados)"),
        ("duplicada_conflitante", "Duplicada com dado conflitante"),
        ("sem_mapeamento", "Sem mapeamento de curso"),
    ]

    tipo = models.CharField(max_length=30, choices=TIPO_CHOICES, verbose_name='Tipo')
    identificador_origem = models.CharField(max_length=50, verbose_name='Identificador de origem')
    codigo = models.CharField(max_length=20, blank=True, verbose_name='Código')
    nome = models.CharField(max_length=200, blank=True, verbose_name='Nome')
    linha_origem = models.PositiveIntegerField(null=True, blank=True, verbose_name='Linha de origem')
    detalhe = models.TextField(
        blank=True,
        help_text="Motivo da ambiguidade, ou comparação da linha conflitante, conforme o tipo.",
        verbose_name='Detalhe',
    )
    dados_brutos = models.JSONField(
        help_text="Linha(s) originais normalizadas, para referência/depuração.",
        verbose_name='Dados brutos',
    )

    resolvido = models.BooleanField(default=False, verbose_name='Resolvido')
    resolvido_em = models.DateTimeField(null=True, blank=True, verbose_name='Resolvido em')
    criado_em = models.DateTimeField(auto_now_add=True, verbose_name='Criado em')

    class Meta:
        verbose_name = "Pendência de importação"
        verbose_name_plural = "Pendências de importação"
        ordering = ["resolvido", "tipo", "linha_origem"]

    def __str__(self):
        return f"[{self.get_tipo_display()}] {self.codigo or self.identificador_origem} (linha {self.linha_origem})"

class BibliografiaReferencia(models.Model):
    """Bibliografia ao nível da matriz de referência — mesmo papel que
    Bibliografia cumpre para ComponenteNaMatriz, mas em nível institucional."""
    TIPO_CHOICES = [("basica", "Básica"), ("complementar", "Complementar")]
    componente_na_matriz_referencia = models.ForeignKey(
        ComponenteNaMatrizReferencia, on_delete=models.CASCADE, related_name="bibliografias",
        verbose_name='Componente na matriz de referência',
    )
    referencia = models.ForeignKey(
        ReferenciaBibliografica, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="bibliografias_matrizes_referencia",
        verbose_name='Referência bibliográfica',
    )
    tipo = models.CharField(max_length=15, choices=TIPO_CHOICES, verbose_name='Tipo')
    titulo = models.CharField(max_length=300, verbose_name='Título')
    autores = models.CharField(max_length=300, verbose_name='Autores')
    editora = models.CharField(max_length=150, blank=True, verbose_name='Editora')
    cidade = models.CharField(max_length=100, blank=True, verbose_name='Cidade')
    ano = models.PositiveIntegerField(blank=True, null=True, verbose_name='Ano')

    class Meta:
        constraints = [models.UniqueConstraint(
            fields=["componente_na_matriz_referencia", "referencia"],
            name="uniq_bibliografia_ref_obra_por_item",
        )]

    def save(self, *args, **kwargs):
        if self.pk:
            anterior = type(self).objects.filter(pk=self.pk).values(
                "componente_na_matriz_referencia_id", "referencia_id", "tipo", "titulo", "autores", "editora", "cidade", "ano"
            ).first()
            if anterior and anterior["referencia_id"] and any(anterior[campo] != getattr(self, campo) for campo in (
                "componente_na_matriz_referencia_id", "referencia_id", "tipo", "titulo", "autores", "editora", "cidade", "ano"
            )):
                raise ValidationError("Esta referência veio da Biblioteca e não pode ser editada. Remova-a e escolha outra obra.")
        super().save(*args, **kwargs)

    def __str__(self):
        return self.titulo

class Chamado(models.Model):
    STATUS_CHOICES = [
        ("pendente", "Pendente"),
        ("resolvido", "Resolvido"),
    ]

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="chamados_abertos",
        verbose_name='Usuário',
    )
    tela = models.CharField(max_length=255, verbose_name='Tela')  # request.path no momento do envio
    mensagem = models.TextField(verbose_name='Mensagem')
    criado_em = models.DateTimeField(auto_now_add=True, verbose_name='Criado em')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pendente", verbose_name='Status')
    resolvido_em = models.DateTimeField(null=True, blank=True, verbose_name='Resolvido em')

    class Meta:
        verbose_name = "Chamado"
        verbose_name_plural = "Chamados"
        ordering = ["-criado_em"]

    def __str__(self):
        return f"Chamado de {self.usuario} em {self.tela} ({self.criado_em:%d/%m/%Y %H:%M})"

class GrupoEquivalenciaComponentes(models.Model):
    """Um conjunto de componentes (de matrizes diferentes) considerados equivalentes entre si."""
    
    criado_em = models.DateTimeField(auto_now_add=True, verbose_name='Criado em')
    history = HistoricalRecords()


class ItemEquivalencia(models.Model):
    grupo = models.ForeignKey(GrupoEquivalenciaComponentes, on_delete=models.CASCADE, related_name='itens', verbose_name='Grupo de equivalência')
    item_matriz = models.ForeignKey(
        'ComponenteNaMatrizReferencia', on_delete=models.CASCADE, related_name='equivalencias',
        verbose_name='Item da matriz',
    )
    ordem = models.PositiveIntegerField(default=1, help_text="Posição da matriz na sequência (a de maior ordem é a que será cadastrada na Resolução)", verbose_name='Ordem')

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['grupo', 'item_matriz'],
                name='uniq_item_equivalencia_grupo_item_matriz',
            ),
            models.UniqueConstraint(
                fields=['grupo', 'ordem'],
                name='uniq_item_equivalencia_grupo_ordem',
            ),
        ]
        ordering = ['ordem']

    def clean(self):
        super().clean()
        # Os grupos legados são preservados; pares explícitos passam pela regra central.


class EquivalenciaMatriz(models.Model):
    """Par direcionado: componente da edição atual e sua equivalência anterior."""
    item_novo = models.ForeignKey(
        ComponenteNaMatrizReferencia, on_delete=models.PROTECT,
        related_name="equivalencias_como_novo",
        verbose_name='Item novo',
    )
    item_anterior = models.ForeignKey(
        ComponenteNaMatrizReferencia, on_delete=models.PROTECT,
        related_name="equivalencias_como_anterior",
        verbose_name='Item anterior',
    )
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="equivalencias_matriz_criadas",
        verbose_name='Criado por',
    )
    criado_em = models.DateTimeField(auto_now_add=True, verbose_name='Criado em')

    class Meta:
        constraints = [models.UniqueConstraint(
            fields=["item_novo", "item_anterior"], name="uniq_equivalencia_matriz_par",
        )]
        ordering = ["item_novo__matriz_id", "item_novo_id", "item_anterior_id"]

    def clean(self):
        super().clean()
        if not self.item_novo_id or not self.item_anterior_id:
            return
        from ppc.services.regras_equivalencia import avaliar_equivalencia
        resultado = avaliar_equivalencia(self.item_anterior, self.item_novo)
        if not resultado["elegivel"]:
            raise ValidationError(resultado["motivos"])

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    history = HistoricalRecords()


class EquivalenciaPPC(models.Model):
    """Par entre vínculo curricular atual e vínculo do PPC predecessor."""
    item_novo = models.ForeignKey(ComponenteNaMatriz, on_delete=models.PROTECT, related_name="equivalencias_ppc_como_novo", verbose_name='Item novo')
    item_anterior = models.ForeignKey(ComponenteNaMatriz, on_delete=models.PROTECT, related_name="equivalencias_ppc_como_anterior", verbose_name='Item anterior')
    criado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="equivalencias_ppc_criadas", verbose_name='Criado por')
    criado_em = models.DateTimeField(auto_now_add=True, verbose_name='Criado em')

    class Meta:
        constraints = [models.UniqueConstraint(fields=["item_novo", "item_anterior"], name="uniq_equivalencia_ppc_par")]
        ordering = ["item_novo__ppc_id", "item_novo_id", "item_anterior_id"]

    def clean(self):
        super().clean()
        if not self.item_novo_id or not self.item_anterior_id:
            return
        from ppc.services.regras_equivalencia import avaliar_equivalencia
        resultado = avaliar_equivalencia(self.item_anterior, self.item_novo)
        if not resultado["elegivel"]:
            raise ValidationError(resultado["motivos"])

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    history = HistoricalRecords()

class ResumoCargaHorariaPPC(models.Model):
    ppc = models.OneToOneField(PPC, on_delete=models.CASCADE, related_name="resumo_carga_horaria", verbose_name='PPC')
    nucleo_livre_manual = models.PositiveIntegerField(default=0, verbose_name='Núcleo livre (manual)')
    acex_nucleo_livre_manual = models.PositiveIntegerField(default=0, verbose_name='ACEx do núcleo livre (manual)')
    acex_extensao_manual = models.PositiveIntegerField(default=0, verbose_name='ACEx de extensão (manual)')
    atividades_complementares_manual = models.PositiveIntegerField(default=0, verbose_name='Atividades complementares (manual)')
    history = HistoricalRecords()

class VinculoUsuarioCurso(models.Model):
    """Quais cursos cada usuário (NDE) pode acessar. Staff (DAA) não precisa de vínculo."""
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='vinculos_curso',
        verbose_name='Usuário',
    )
    curso = models.ForeignKey(Curso, on_delete=models.CASCADE, related_name='vinculos_usuarios', verbose_name='Curso')
    criado_em = models.DateTimeField(auto_now_add=True, verbose_name='Criado em')

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['usuario', 'curso'], name='uniq_vinculo_usuario_curso'),
        ]
        ordering = ['usuario__username', 'curso__nome']

    history = HistoricalRecords()

    def __str__(self):
        return f"{self.usuario} → {self.curso.nome}"


class RevisaoSecaoPPC(models.Model):
    """Confirmação de que o NDE revisou uma seção do PPC. Independe de a seção estar preenchida."""
    ppc = models.ForeignKey(PPC, on_delete=models.CASCADE, related_name="revisoes_secao", verbose_name='PPC')
    secao = models.CharField(max_length=50, verbose_name='Seção')
    conteudo_hash = models.CharField(max_length=64, verbose_name='Hash do conteúdo')
    revisado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+",
        verbose_name='Revisado por',
    )
    revisado_em = models.DateTimeField(auto_now=True, verbose_name='Revisado em')

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['ppc', 'secao'], name='uniq_revisao_secao_ppc'),
        ]

    history = HistoricalRecords()

    def __str__(self):
        return f"{self.ppc} — {self.secao}"

class EventoUso(models.Model):
    """Log append-only de acessos e ações de negócio. Edições de campos ficam em EventoEdicao."""

    class Tipo(models.TextChoices):
        LOGIN = "login", "Login"
        LOGOUT = "logout", "Logout"
        LOGIN_FALHOU = "login_falhou", "Falha de login"
        PPC_DUPLICADO = "ppc_duplicado", "PPC duplicado"
        PPC_REVERTIDO = "ppc_revertido", "PPC revertido"
        PDF_GERADO = "pdf_gerado", "PDF gerado"
        MATRIZ_APLICADA = "matriz_aplicada", "Matriz aplicada ao PPC"
        IMPORTACAO = "importacao", "Importação"
        MATRIZ_DUPLICADA = "matriz_duplicada", "Matriz de referência duplicada"

    # tipos sujeitos à retenção de 12 meses
    TIPOS_ACESSO = ("login", "logout", "login_falhou")

    tipo = models.CharField(max_length=30, choices=Tipo.choices, verbose_name='Tipo')
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
        verbose_name='Usuário',
    )
    identificador = models.CharField(max_length=150, blank=True, help_text="Só em falha de login: o username digitado.", verbose_name='Identificador')
    curso = models.ForeignKey(Curso, on_delete=models.SET_NULL, null=True, blank=True, related_name="+", verbose_name='Curso')
    ppc = models.ForeignKey(PPC, on_delete=models.SET_NULL, null=True, blank=True, related_name="+", verbose_name='PPC')
    metadados = models.JSONField(default=dict, blank=True, verbose_name='Metadados')
    criado_em = models.DateTimeField(auto_now_add=True, verbose_name='Criado em')

    class Meta:
        ordering = ["-criado_em"]
        indexes = [
            models.Index(fields=["tipo", "criado_em"]),
            models.Index(fields=["usuario", "criado_em"]),
        ]


class EventoEdicao(models.Model):
    """Uma edição real (o save mudou algo) em modelo rastreado. Alimentado por signal do simple_history."""
    TIPO_CHOICES = [("criacao", "Criação"), ("edicao", "Edição"), ("exclusao", "Exclusão")]

    modelo = models.CharField(max_length=60, verbose_name='Modelo')          # ex.: 'ppc.PPC'
    objeto_id = models.PositiveIntegerField(verbose_name='ID do objeto')
    history_id = models.PositiveIntegerField(verbose_name='ID do histórico')
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES, verbose_name='Tipo')
    campos = models.JSONField(default=list, blank=True, verbose_name='Campos')  # [] = não se sabe quais (ou criação/exclusão)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+", verbose_name='Usuário')
    ppc = models.ForeignKey(PPC, on_delete=models.SET_NULL, null=True, blank=True, related_name="+", verbose_name='PPC')
    curso = models.ForeignKey(Curso, on_delete=models.SET_NULL, null=True, blank=True, related_name="+", verbose_name='Curso')
    matriz = models.ForeignKey(MatrizReferenciaCurricular, on_delete=models.SET_NULL, null=True, blank=True, related_name="+", verbose_name='Matriz')
    ocorreu_em = models.DateTimeField(db_index=True, verbose_name='Ocorreu em')  # = history_date (preserva a data original no backfill)

    class Meta:
        ordering = ["-ocorreu_em"]
        constraints = [
            models.UniqueConstraint(fields=["modelo", "history_id"], name="uniq_evento_edicao_historico"),
        ]
        indexes = [
            models.Index(fields=["ppc", "ocorreu_em"]),
            models.Index(fields=["curso", "ocorreu_em"]),
            models.Index(fields=["usuario", "ocorreu_em"]),
            models.Index(fields=["matriz", "ocorreu_em"]),
        ]


class UsoDiario(models.Model):
    """Contador de páginas vistas por usuário/dia/hora/tela (data e hora já no fuso local)."""
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+", verbose_name='Usuário')
    data = models.DateField(verbose_name='Data')
    hora = models.PositiveSmallIntegerField(verbose_name='Hora')  # 0-23
    url_name = models.CharField(max_length=100, verbose_name='Nome da rota')
    contagem = models.PositiveIntegerField(default=0, verbose_name='Contagem')

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["usuario", "data", "hora", "url_name"], name="uniq_uso_diario"),
        ]
