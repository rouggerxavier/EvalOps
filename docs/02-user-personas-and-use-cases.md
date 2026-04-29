# 02 — Personas & Use Cases

## 1. Personas

### 1.1 Marina — AI Engineer em produto

- **Idade/contexto:** 28 anos, ~4 anos de back-end Python, 1 ano focada em LLMs.
- **Trabalha em:** startup B2B com agente de atendimento.
- **Dores:**
  - "Trocamos de `gpt-4o` para `gpt-4o-mini` para economizar e o NPS caiu, mas demoramos 3 semanas para descobrir."
  - "Não sei exatamente quanto cada feature está custando em LLM."
  - "Quando o agente alucina, eu descubro pelo Slack do cliente, não pelo monitoramento."
- **O que ela quer do EvalOps:** instrumentar em 10 min, ter dashboard de qualidade que ela mostra para o CTO, e regression test no CI.
- **Frequência de uso:** diária (dashboard) + por release (regression).

### 1.2 Ricardo — Tech Lead / Staff Engineer

- **Idade/contexto:** 36 anos, lidera time de 5 engenheiros, responsável por arquitetura e custo.
- **Dores:**
  - "Preciso justificar para finance por que estamos gastando USD 8k/mês em OpenAI."
  - "Quero comparar Gemini vs OpenAI antes de migrar, não depois."
  - "Cada engenheiro inventa um jeito de logar prompt; nada consolidado."
- **O que ele quer:** experiments de comparação A/B entre providers, breakdown de custo por feature, SLA de qualidade automatizado.
- **Frequência de uso:** semanal (relatórios) + ad-hoc (decisões de arquitetura).

### 1.3 Sofia — Product Manager de produto com IA

- **Idade/contexto:** 31 anos, vinda de produto SaaS clássico, aprendeu IA na marra.
- **Dores:**
  - "Como sei se o agente está atendendo bem? Quantas conversas terminam mal?"
  - "Não tenho como pedir ao time de eng anotação de qualidade — eles odeiam."
- **O que ela quer:** view simplificada de "saúde do produto IA" com % de respostas boas, feed de exemplos ruins para entender padrão.
- **Frequência de uso:** 2-3x/semana, foco em dashboard, raramente toca em rubrica.

### 1.4 João — Profissional em transição para AI Engineer (persona de portfólio)

- **Contexto:** desenvolvedor full-stack querendo entrar em AI Engineering.
- **Dores:** projetos de portfólio dele "só chamam a API da OpenAI"; precisa demonstrar profundidade.
- **O que ele quer:** usar o EvalOps Studio para instrumentar seus próprios projetos (DocOps, ImobiliarIA, Aurora) e ter screenshots para LinkedIn/portfólio mostrando que entende LLMOps.
- **Frequência de uso:** intensa em sprints de portfólio, depois manutenção.

> **Nota:** A persona João é o **autor real do projeto**. As demais são personas de uso simulado para guiar decisões de UX. A persona Marina é a **persona primária do MVP**.

## 2. Casos de uso (user stories detalhadas)

### UC-01 — Instrumentação inicial de um agente

**Como** Marina,
**eu quero** instrumentar meu agente Python em produção,
**para** começar a coletar traces sem refatorar nada.

**Fluxo feliz:**
1. Marina cria conta no EvalOps (magic link).
2. Cria projeto "Aurora-Support".
3. Gera API key; copia para `.env`.
4. `pip install evalops` e adiciona no código:
   ```python
   import evalops
   evalops.init(api_key=os.getenv("EVALOPS_API_KEY"), project="aurora-support")

   @evalops.trace(name="answer_user_question")
   def answer(user_msg: str) -> str:
       ...
   ```
5. Faz deploy. Em < 1 min, traces aparecem no dashboard.

**Critérios de aceite:**
- ≤ 3 linhas para instrumentação básica.
- Falha do EvalOps NÃO quebra o agente (SDK silencioso).
- Trace contém prompt, resposta, modelo (auto-detectado se usa OpenAI/Anthropic/Gemini SDK), tokens, custo, latência.

### UC-02 — Eval automático em produção

**Como** Marina,
**eu quero** que cada resposta do agente seja avaliada automaticamente por uma rubrica,
**para** detectar queda de qualidade sem revisar à mão.

**Fluxo:**
1. Marina escreve `rubrics/answer_quality.yaml` no repo dela.
2. Faz `evalops rubrics push` (CLI) — sobe para o projeto.
3. Em "Settings → Auto-eval", marca: "rodar `answer_quality` em todo trace de span_type `llm_call` e tag `production`".
4. A cada novo trace que casa, worker dispara a rubrica.
5. Score aparece no detalhe do trace e no overview.

**Critérios de aceite:**
- Rubrica YAML é validada no push (schema strict).
- Eval roda em < 30s p95 do trace ingerido.
- Falha do judge LLM NÃO trava o trace; eval fica `status=error`, trace continua íntegro.

### UC-03 — Regression test em CI antes de deploy

**Como** Ricardo,
**eu quero** rodar o golden-set em CI a cada PR,
**para** bloquear deploys que pioram qualidade.

**Fluxo:**
1. Ricardo define golden-set: 50 pares `(input, expected_intent, must_contain_keywords)` no projeto.
2. Define experiment "regression-prod" com critério: ≥ 95% dos casos passam rubrica `intent_match`.
3. No GitHub Action:
   ```yaml
   - run: evalops experiment run regression-prod --prompt-version $GITHUB_SHA --fail-on-regression
   ```
4. Se score do PR < score da main em > 2pp, action falha.

**Critérios de aceite:**
- CLI retorna exit code 1 em regression.
- Relatório acessível por URL pública (PR comment).

### UC-04 — Comparar providers para decisão de migração

**Como** Ricardo,
**eu quero** rodar mesmo dataset em OpenAI e Gemini,
**para** decidir migração com dados.

**Fluxo:**
1. Ricardo escolhe dataset "production-sample-1k" (sample de 1000 traces reais redatados).
2. Cria experiment com 2 variants: `(prompt-v3, gpt-4o-mini)` e `(prompt-v3, gemini-2.5-flash)`.
3. Roda. Dashboard mostra: score médio, custo total, latência p95, % falhas, exemplos de divergência.

**Critérios de aceite:**
- Comparação visual lado a lado.
- Export do relatório em PDF/Markdown (Futuro).

### UC-05 — Sofia revisando qualidade semanal

**Como** Sofia,
**eu quero** ver as 20 piores conversas da semana,
**para** entender padrões de falha do produto.

**Fluxo:**
1. Sofia entra no projeto, aba "Review".
2. Filtros pré-selecionados: últimos 7 dias, score < 0.5, sem feedback humano.
3. Clica em um trace → vê conversa completa, motivo do score baixo (reasoning do judge), botões de feedback.
4. Marca tag "alucinação_preço".
5. Exporta tabela de tags da semana.

### UC-06 — Coleta de feedback do usuário final

**Como** Marina,
**eu quero** que 👍/👎 do usuário no chat virem dataset,
**para** treinar/few-shot melhorias.

**Fluxo:**
1. No frontend do agente, ao receber resposta:
   ```js
   await evalops.feedback({ trace_id, thumbs: "down", comment: "respondeu errado o horário" });
   ```
2. EvalOps registra `human_feedback` ligado ao trace.
3. Marina no dashboard filtra: "feedback negativo + tag X".
4. Clica "Export to JSONL" → baixa arquivo pronto para fine-tuning.

### UC-07 — João (portfólio) — demo do projeto

**Como** João,
**eu quero** mostrar EvalOps instrumentando meus 3 projetos ao vivo,
**para** impressionar em entrevista.

**Fluxo:**
1. João instrumenta DocOps, ImobiliarIA e Aurora apontando para um único projeto EvalOps de demo.
2. Roda interações reais por 1 semana.
3. Print do dashboard com traces de 3 origens, custo agregado, scores por origem.
4. Liga rubrica diferente para cada (`docops_summary_quality`, `imobiliaria_intent_capture`, `aurora_helpfulness`).

**Critérios de aceite:**
- Dashboard suporta filtro por `service` ou tag para diferenciar origens.
- Telemetria de custo agregada vs por-projeto.

## 3. Anti-casos de uso (não otimizar para)

- Empresa que quer logar **toda** chamada de LLM de uma org de 1000 engenheiros (escala de Honeycomb/Datadog).
- Time que quer um **chat UI** para conversar com seus modelos (não é OpenWebUI/ChatUI).
- Quem quer **fine-tuning gerenciado** (não é HuggingFace AutoTrain).
- Quem quer **um agente pronto** (não é AutoGen/CrewAI).
