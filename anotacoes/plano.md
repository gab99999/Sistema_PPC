# Projeto: Sistema de Gerenciamento de PPCs (UFCAT)

## Contexto e objetivo

Sistema web para gerenciar a elaboração e atualização dos Projetos Pedagógicos de Curso (PPCs) da UFCAT, com banco de dados por trás. Substitui o antigo projeto de automatização do SIGAA (cancelado pelo supervisor) — mantém partes da lógica (separação de camadas, modelo de dados estruturado), mas é um projeto novo e mais amplo.

**Domínio já disponível:** `trilhasre.org/sistema_PPC/` — atualmente vazio, nada implementado ainda. Acesso via WinSCP (FTP/SFTP).

**Funcionalidades principais:**
1. Cadastro estruturado dos dados de um PPC (formulários por seção)
2. Geração de documento final (PDF) a partir dos dados cadastrados
3. Caminho inverso: importar um documento PPC existente e popular o banco automaticamente
4. Atualização/versionamento de PPCs ao longo do tempo

**Referência de funcionamento:** documento passo a passo do sistema SISPPC da UFG (enviado por Alice), que já usa essa lógica em produção. Serve como mapa da estrutura de dados e do fluxo de telas — não é pra copiar plugin/código, é referência de requisitos.

**Pessoas envolvidas:** Alice + um professor orientando, que pediu explicitamente para construir do zero (sem CMS ou plugins prontos), com base em experiência ruim com plugins em projeto anterior.

---

## Decisões de arquitetura já tomadas

- **Back-end: Django.** Escolhido em vez de Flask porque o projeto é essencialmente CRUD-pesado (muitos formulários, muitos campos estruturados), e o Django Admin gera interface de cadastro/edição automaticamente a partir dos models — evita reescrever telas de formulário na mão. Custo: expõe Alice a classes/herança (OOP) antes da matéria formal, mas de forma progressiva e com apoio.
- **Geração de PDF: WeasyPrint** (HTML/CSS → PDF via template Jinja2/Django Templates). Escolhido em vez de ReportLab por ser mais fácil de iterar visualmente (testa como HTML antes de virar PDF).
- **Banco de dados:** a confirmar (MySQL ou PostgreSQL — já existe um banco SQL disponível no domínio, falta confirmar qual).
- **Hospedagem:** ainda não confirmado se o servidor do domínio suporta Python/WSGI nativamente (verificar painel de controle tipo cPanel/Plesk, procurar opção "Setup Python App" ou confirmar com a administração do domínio na UFCAT/DTI).
- **Princípio geral (herdado do projeto SIGAA):** construir do zero, sem dependência de plugins ou CMS de terceiros — alinhado tanto com a preferência de Alice por ferramentas simples e apropriadas ao estágio quanto com o pedido explícito do professor orientando.

## Modelo de dados (rascunho, baseado no SISPPC/UFG)

Duas famílias de dados:

1. **Seções textuais do PPC** (~15 campos de texto longo): Informações Gerais, Apresentação, Exposição de Motivos, Objetivos, Princípios, Expectativas, TCC, Estágio Curricular, Atividade Complementar, Integração Ensino/Pesquisa/Extensão, Avaliação do Processo de Ensino-Aprendizagem, Avaliação do Projeto de Curso, Qualificação de Docentes e TA, Requisitos Legais e Normativos, Referências.
2. **Estrutura curricular** (relacional, mais complexa): Curso → Períodos → Componentes Curriculares (natureza, núcleo, carga horária teórica/prática, ementa) → Bibliografia Básica/Complementar (título, autores, edição, cidade, editora, ano).

---

## Fases do projeto (rascunho inicial)

- **Fase 0 (atual):** Levantamento e modelagem de dados — desenhar o schema completo a partir do documento de referência da UFG, confirmar stack de hospedagem (Python? qual banco?).
- **Fase 1:** Modelo de dados em Django (`models.py`) para as duas famílias de dados.
- **Fase 2:** CRUD via Django Admin (customizado) para cadastro/edição.
- **Fase 3:** Geração de PDF a partir dos dados (template Jinja2/Django + WeasyPrint).
- **Fase 4:** Caminho inverso — importar documento existente e popular o banco.
- **Fase 5:** Atualização/versionamento de PPCs (histórico de mudanças, comparação entre versões — possível reaproveitamento de lógica do projeto SIGAA com `difflib`).
- **Fase 6 (futuro/opcional):** Melhorias de UX nos formulários, autenticação de usuários por curso/unidade acadêmica.
- **Fase 7:** Agente de Revisão de PPC (grammar + coerência via INEP)

---

## Notas de aprendizado

- Django será a primeira exposição prática de Alice a classes/herança em Python (via `models.Model`), antes da matéria formal de OOP — explicações devem conectar isso ao que ela já viu (ex: paralelo com estrutura de dicts usada no Terceira Lua).
- O documento da UFG (SISPPC) é a principal fonte de verdade pra escopo de campos e regras de negócio (ex: carga horária mínima de Núcleo Livre = 128h, carga horária de atividades complementares ≥ 100h, etc. — essas regras podem virar validações no Django).