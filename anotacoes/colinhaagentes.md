# Colinha — AI Agent Developer Specialization

> Referência enxuta de código e conceitos. Vai crescendo módulo a módulo.

---

## 📍 Módulo 1 — Utilizando APIs de LLM

### API vs produto (ChatGPT/Claude.ai)
- O **site/app** (ChatGPT, Claude.ai) e a **API** são produtos diferentes.
- Assinatura do site **não** dá créditos de API — API é pay-as-you-go.
- Alternativas com **tier gratuito** pra estudar: Groq, Gemini API, OpenRouter, HuggingFace Inference.

### Setup básico com Groq (compatível com SDK da OpenAI)
```python
from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv()  # lê o arquivo .env e carrega variáveis de ambiente

client = OpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1"  # muda o "destino" da chamada
)

response = client.chat.completions.create(
    model="llama-3.3-70b-versatile",
    messages=[
        {"role": "user", "content": "Olá!"}
    ]
)

print(response.choices[0].message.content)
```
- `load_dotenv()` → carrega variáveis do `.env` (evita hardcodar API key no código).
- `os.getenv("X")` → lê variável de ambiente.
- `base_url` → é o truque: a Groq imita o formato da API da OpenAI, então só troca o endereço + a key.
- `response.choices[0].message.content` → caminho padrão pra pegar o texto da resposta.

### LiteLLM (camada de abstração entre provedores)
```python
from litellm import completion

response = completion(
    model="groq/llama-3.3-70b-versatile",
    messages=messages,
    api_key=os.getenv("GROQ_API_KEY")
)
```
Vantagem: trocar de provedor (OpenAI, Groq, Gemini, Claude, Ollama...) mudando só o **nome do modelo**, sem reescrever a lógica.

---

## 📍 JSON — objeto Python ↔ string ↔ arquivo

```
Python dict  →  json.dumps()  →  JSON string
JSON string  →  json.loads()  →  Python dict
Python dict  →  json.dump()   →  arquivo .json
arquivo .json → json.load()   →  Python dict
```
Regra prática: **dumps/loads** = strings em memória. **dump/load** (sem "s") = arquivo em disco.

---

## 📍 Estrutura de mensagens (roles)

```python
messages = [
    {"role": "system", "content": "Você é um assistente..."},  # regras/comportamento
    {"role": "user", "content": "pergunta do usuário"},          # input
    {"role": "assistant", "content": "resposta anterior"}        # memória/histórico
]
```
- `messages.append(...)` é o jeito mais simples de construir memória — vai empilhando o histórico em vez de reconstruir tudo a cada chamada.

### ⚠️ Erro comum
```python
d = [response]   # ❌ isso cria uma LISTA, não uma string
d = response      # ✅ correto — role "assistant" espera content como string
```

---

## 📍 Sequential Prompting (encadear prompts)

Fluxo típico de um exercício:
```
Prompt 1 → gerar função
Prompt 2 → documentar a função
Prompt 3 → adicionar unittest
```
Melhor prática: manter **um único histórico** (`messages.append`) em vez de recomeçar a conversa a cada prompt — assim o modelo mantém contexto do que já foi gerado.

### Extraindo código da resposta do modelo
```python
def extract_code_block(response: str):
    if not '```' in response:
        return response

    code_block = response.split('```')[1].strip()

    if code_block.startswith("python"):
        code_block = code_block[6:]  # remove a palavra "python" do markdown

    return code_block
```
- `.split('```')[1]` → pega o conteúdo entre o 1º e 2º ` ``` `
- `.strip()` → remove espaços/quebras de linha nas pontas
- `.startswith("python")` → checa se o bloco começa com a linguagem declarada (ex: ` ```python `)

---

## 📍 AI Agent Loop (o ciclo básico de um agente)

```
Construct Prompt
      ↓
Generate Response (LLM)
      ↓
Parse Response
      ↓
Execute Action
      ↓
Convert Result to String
      ↓
Continue Loop
```
Esse é o padrão que se repete em praticamente toda arquitetura de agente — vale gravar.

---

## 📍 Tool Definition & Function Calling

### Definindo uma tool (JSON Schema)
```python
{
    "tool_name": "read_file",
    "args": {
        "file_name": "teste.py"
    }
}
```
`args` não é nada místico — são só os **argumentos da função** que a tool vai executar.

### Antes × Depois do Function Calling
```
ANTES:  Prompt Engineering → LLM devolve texto → parsing manual com json.loads()
DEPOIS: Function Calling   → LLM devolve tool_calls estruturado → sem parsing manual
```

```python
response = completion(
    model="openai/gpt-4o",
    messages=messages,
    tools=tools
)

tool = response.choices[0].message.tool_calls[0]
```
Function calling funciona em vários provedores (GPT, Claude, Gemini, Groq, Ollama, Llama local), desde que o modelo suporte.

---

## 📍 Python OOP essencial (pré-requisito pra entender os agentes)

> Como POO só vem no próximo semestre, aqui vai o mínimo pra ler o código dos agentes sem travar.

### Decorators (`@`)
```python
@register_tool(...)
def read_file():
    ...

# É exatamente equivalente a:
read_file = register_tool(...)(read_file)
```
Um decorator **modifica ou registra** uma função antes dela ser usada.

### `__init__` e dunder methods
```python
class Agent:
    def __init__(self, name):
        self.name = name  # roda automaticamente quando você faz Agent("nome")
```
- `__init__` executa automaticamente na criação do objeto (`Classe(...)`).
- `__` (dunder methods) = métodos especiais: `__init__`, `__str__`, `__len__`, `__getitem__`, etc.

### Referência vs execução
```python
planner.run    # referência ao método (não executa)
planner.run()  # executa o método
```

### Metadata
"Metadata" = dados sobre dados. No contexto de tools: nome, descrição, parâmetros, type hints — tudo que descreve a função sem ser a função em si.

---

## 📍 Self-Prompting

O agente principal continua como **coordenador**; tarefas especializadas ficam encapsuladas em ferramentas que, por dentro, fazem outro prompt pra um LLM.

Analogia: **CEO → especialistas**.

```python
def prompt_llm_for_json(schema, prompt):
    # chama o LLM pedindo resposta em formato estruturado
    response = ...  # LLM retorna JSON
    return json.loads(response)  # vira dict
```
Trade-off: ferramenta genérica (flexível, mas menos precisa) × ferramenta especializada (precisa, mas limitada a um caso).

---

## 📍 Arquitetura de Agente

A **API não é o agente** — é só o modelo. O agente é a arquitetura construída em cima:

```
Agent
 ├── Memory
 ├── Goals
 ├── Environment
 ├── Action Registry
 └── LLM
```

### Factory function
```python
def create_agent(config):
    # fábrica: cria agentes reaproveitando configuração
    return Agent(**config)
```
Permite criar múltiplos agentes (ex: 3 agentes resolvendo o mesmo problema → comparar respostas → votação).

### Registry (padrão comum em frameworks de agente)
```python
class AgentRegistry:
    def __init__(self):
        self.agents = {}

    def register_agent(self, name, agent):
        self.agents[name] = agent

    def get_agent(self, name):
        return self.agents[name]
```

### Memory
```python
class Memory:
    def __init__(self):
        self.items = []
```
`Memory()` cria um objeto vazio que só armazena histórico. O framework depois monta o prompt assim:
```python
messages = agent_rules + memory.items
response = completion(model=..., messages=messages)
```

---

## 📍 Multi-Agent — padrões de compartilhamento de memória

| Padrão | O que acontece |
|---|---|
| **Message Passing** | Memória nova a cada agente; retorna só o resultado |
| **Memory Reflection** | Memória nova, mas depois copia o raciocínio do agente anterior |
| **Memory Handoff** | Agentes compartilham exatamente a mesma memória |
| **Selective Memory Sharing** | Cada item de memória ganha um ID → LLM escolhe quais são relevantes → cria memória nova só com o que importa → guarda justificativa da escolha |

Vantagem do Selective Sharing: menos contexto, menos ruído, seleção inteligente.

---

## 📍 MATE (checklist de boas práticas em agentes)

- **M**odel Efficiency → modelo pequeno pra tarefa simples, modelo grande pra tarefa difícil
- **A**ction Specificity → preferir ferramentas específicas a ferramentas genéricas
- **T**oken Efficiency → não desperdiçar tokens, pedir só o necessário
- **E**nvironmental Safety → validação, permissões, reversibilidade, proteção contra ações perigosas

---

## 📍 ActionContext & Dependency Injection

### Problema que resolve
Se a tool acessa recursos do Agent diretamente (`memory = agent.memory`), ela fica **acoplada** à implementação do Agent — qualquer mudança lá quebra a tool.

### Solução: ActionContext
Um contêiner que **transporta** dependências compartilhadas (não as cria):
```python
ActionContext({
    "memory": memory,
    "llm": generate_response,
    "auth_token": "...",
    "config": ...
})
```

A tool recupera o que precisa sem saber de onde veio:
```python
memory = action_context.get_memory()

for mem in memory.get_memories():
    # cada item: {"type": "user"/"assistant", "content": "..."}
    ...
```

### Quem injeta é o Environment, não o Agent
```
Usuário → Agent → Environment → Tool
```
- **Agent** só decide qual tool chamar e manda `ActionContext` + `Tool` + argumentos (vindos do LLM).
- **Environment** usa `inspect.signature()` pra olhar os parâmetros da função e injetar automaticamente:
  - `action_context` → se o parâmetro existir na assinatura
  - parâmetros que começam com `_` (ex: `_auth_token`) → busca em `action_context.properties[...]`

```python
def update_profile(action_context, username, _auth_token):
    ...

# LLM só precisa fornecer: {"username": "João"}
# Environment completa o resto automaticamente:
update_profile(username="João", action_context=context, _auth_token="abc123")
```

**Regra-chave:** parâmetro começando com `_` não aparece no schema enviado ao LLM — ele nunca vê nem inventa tokens/conexões/configs. Isso é o que mantém a arquitetura segura.

### Separação de responsabilidades (resumo)
| Componente | Responsabilidade |
|---|---|
| Agent | Decide qual Tool executar |
| Environment | Faz Dependency Injection + executa a Tool |
| ActionContext | Armazena recursos compartilhados |
| Tool | Só executa a própria lógica |

---

## 📍 Capabilities (plugar comportamento sem mexer no Agent)

Capabilities adicionam funcionalidade ao Agent Loop via **hooks**, sem alterar o código do Agent:
```
init()
process_prompt()
process_response()
process_action()
process_result()
end_agent_loop()
```

### PlanFirstCapability
Roda `create_plan()` dentro do `init()` — antes de qualquer ação. Analisa tarefa + memória + ferramentas disponíveis, gera um plano, e salva na memória como tipo `"system"`. O Agent consulta esse plano durante toda a execução.
```
Planejar → Executar
```
Evita ações aleatórias, dá visão estratégica.

### ProgressTrackingCapability
Roda `track_progress()` no hook `end_agent_loop()` (a cada iteração ou a cada N). Gera um relatório (progresso, tarefas concluídas, bloqueios, próximos passos) e salva na memória.
```
Planejar → Executar → Refletir → Ajustar → Continuar
```
Evita repetir ações, adapta o plano, mantém histórico de decisões.

---

## 📎 Links úteis
- Groq Console (API Key): https://console.groq.com/keys
- LiteLLM Providers: https://docs.litellm.ai/docs/providers
- OpenAI API Error Codes: https://platform.openai.com/docs/guides/error-codes/api-errors

---

*Última atualização: ActionContext, Dependency Injection, Environment e Capabilities (PlanFirst, ProgressTracking). Próxima entrada: a definir.*