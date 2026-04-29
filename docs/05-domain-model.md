# 05 — Domain Model

Modelo de domínio em DDD-lite. Foco em **entidades**, **agregados**, **invariantes** e **regras de negócio** — independente de DB ou framework.

## 1. Bounded contexts

| Contexto | Responsabilidade |
|---|---|
| **Identity** | usuários, organizações, autenticação, membership |
| **Access** | API keys, scopes, rate limits |
| **Tracing** | traces, spans, events (ingestion + leitura) |
| **Evaluation** | rubrics, evaluators, evaluation runs, scores |
| **Versioning** | prompts, prompt_versions, datasets, experiments |
| **Feedback** | human feedback, reviews, annotations |
| **Datasets / Export** | export jobs, dataset snapshots |
| **Billing** | plans, subscriptions, usage counters (mockado MVP) |

> Os contextos compartilham `organization_id` mas não devem acessar tabelas uns dos outros diretamente. Comunicação inter-contexto via **services** ou **eventos de domínio**.

## 2. Entidades & agregados

### 2.1 Identity
```
User (root)
  id: ULID
  email: str (unique)
  name: str
  email_verified_at: datetime?
  created_at, updated_at

Organization (root)
  id: ULID
  name: str
  slug: str (unique)
  created_at, updated_at

Membership
  user_id, organization_id, role: enum(owner, admin, member, viewer)
  PRIMARY KEY (user_id, organization_id)
```

**Invariantes:**
- I-01: Toda User tem ≥ 1 Organization (criada automaticamente no signup como `slug = user-{id}` ou nome customizado).
- I-02: Toda Organization tem ≥ 1 owner. Removendo último owner é proibido.
- I-03: `email` é único globalmente (case-insensitive).

### 2.2 Project & Access
```
Project (root, dentro do agregado Organization)
  id: ULID
  organization_id: FK
  name: str
  slug: str (unique within org)
  description: str?
  default_environment: enum(dev, staging, prod) = "prod"
  retention_days: int = 90
  redaction_enabled: bool = false
  created_at, updated_at, archived_at?

ApiKey
  id: ULID
  project_id: FK
  prefix: str (e.g., "evk_live_a1b2")  -- mostrado em listagem
  hash: str (argon2id)
  name: str
  environment: enum
  scopes: array<str>  -- ["ingest", "read"]
  rate_limit_per_minute: int = 60
  last_used_at: datetime?
  revoked_at: datetime?
  created_at
```

**Invariantes:**
- I-10: `Project.slug` é único dentro da organização.
- I-11: ApiKey só é válida se `revoked_at IS NULL` E `Project.archived_at IS NULL`.
- I-12: Hash da key é gerado uma única vez; raw key NÃO é persistida.
- I-13: Rate limit é por (api_key, minuto). Excedido → 429.

### 2.3 Tracing
```
Trace (root)
  id: ULID
  project_id: FK
  client_trace_id: str?  -- idempotência
  name: str  -- e.g., "answer_user_question"
  service: str?  -- "aurora-support", "docops-agent"
  environment: enum
  status: enum(ok, error, partial)
  started_at, ended_at: datetime
  duration_ms: int  -- denormalized
  total_tokens_in, total_tokens_out: int
  total_cost_usd: decimal(10,6)
  tags: jsonb  -- {"feature": "summary", "user_id_hash": "..."}
  user_ref: str?  -- hash/anon ID do end-user
  metadata: jsonb
  created_at

Span (parte do agregado Trace)
  id: ULID
  trace_id: FK
  parent_span_id: FK?  -- para árvore
  type: enum(llm_call, tool_call, retrieval, embedding, agent_step, chain)
  name: str
  status: enum(ok, error)
  started_at, ended_at: datetime
  duration_ms: int
  -- LLM call fields
  provider: str?  -- "openai", "google"
  model: str?  -- "gpt-4o-mini"
  prompt_version_id: FK?  -- liga ao versioning
  messages_in: jsonb?  -- [{role, content}]
  messages_out: jsonb?
  tools: jsonb?
  tokens_in, tokens_out: int?
  cost_usd: decimal(10,6)?
  fallback_from_span_id: FK?  -- se foi fallback, aponta para o span original
  -- Tool/retrieval fields
  input: jsonb?
  output: jsonb?
  error: jsonb?  -- {type, message, stack}
  metadata: jsonb

Event (filho de Span)
  id: ULID
  span_id: FK
  type: str  -- "fallback_triggered", "guardrail_blocked", "cache_hit"
  occurred_at: datetime
  payload: jsonb
```

**Invariantes:**
- I-20: `Trace.duration_ms = max(spans.ended_at) - min(spans.started_at)` (calculado em ingestion).
- I-21: `Trace.total_*` é somatório dos spans (calculado em ingestion).
- I-22: `Span.parent_span_id` deve apertar a um span do mesmo trace.
- I-23: `Trace.client_trace_id` único por `(project_id, client_trace_id)` quando preenchido.
- I-24: Spans não podem ser editados após criação. Para correção, usar evento de domínio `trace.corrected`.

### 2.4 Evaluation
```
Rubric (root)
  id: ULID
  project_id: FK
  slug: str
  description: str?
  current_version: int
  created_at

RubricVersion
  id: ULID
  rubric_id: FK
  version: int  -- 1, 2, 3...
  yaml_source: text
  parsed_spec: jsonb
  created_at, created_by: FK<User>
  archived_at: datetime?

Evaluator (parte de RubricVersion, normalizado)
  id: ULID
  rubric_version_id: FK
  type: enum(llm_judge, regex_match, keyword_presence, length_bounds, json_schema_valid, exact_match, cosine_similarity)
  config: jsonb  -- prompt template, threshold, etc.
  weight: float = 1.0
  fail_fast: bool = false

EvaluationRun (root)
  id: ULID
  project_id: FK
  trace_id: FK
  rubric_id: FK
  rubric_version: int
  triggered_by: enum(api, auto, schedule, experiment)
  status: enum(queued, running, completed, error)
  aggregate_score: float?  -- 0..1
  passed: bool?
  cost_usd: decimal
  latency_ms: int
  started_at, completed_at: datetime
  error: jsonb?

EvaluationScore (parte de EvaluationRun)
  id: ULID
  run_id: FK
  evaluator_id: FK
  score: float
  passed: bool
  reasoning: text?
  raw_output: jsonb?
  cost_usd: decimal
  latency_ms: int
```

**Invariantes:**
- I-30: RubricVersion é imutável após criada.
- I-31: `aggregate_score = aggregate(scores, method)`. Default `method = weighted_mean`.
- I-32: `passed = aggregate_score >= rubric.threshold` (default 0.7).
- I-33: Run com status=`error` ainda persiste scores parciais coletados antes do erro.

### 2.5 Versioning
```
Prompt (root)
  id: ULID
  project_id: FK
  slug: str  -- "support-answer-system"
  current_version: int
  created_at

PromptVersion
  id: ULID
  prompt_id: FK
  version: int
  template: text  -- com placeholders {var}
  variables: jsonb  -- schema das vars
  metadata: jsonb  -- {model_default, temperature_default, ...}
  changelog: text?
  created_at, created_by

Dataset (root)
  id: ULID
  project_id: FK
  slug: str
  description: str?
  source: enum(manual, from_traces, uploaded)
  created_at

DatasetItem
  id: ULID
  dataset_id: FK
  input: jsonb  -- {messages, context, ...}
  expected_output: jsonb?
  metadata: jsonb
  source_trace_id: FK?

Experiment (root)
  id: ULID
  project_id: FK
  name: str
  dataset_id: FK
  variants: jsonb  -- [{name, prompt_version_id, model, params}]
  rubric_id: FK
  pass_criteria: jsonb  -- {"min_pass_rate": 0.95}
  baseline_variant: str?

ExperimentRun
  id: ULID
  experiment_id: FK
  status: enum(queued, running, completed, error)
  results: jsonb  -- por variant: {pass_rate, avg_score, total_cost}
  passed: bool?
  triggered_by: enum(api, ci, manual)
  created_at, completed_at
```

**Invariantes:**
- I-40: PromptVersion imutável.
- I-41: Experiment.variants tem ≥ 2 entries OU 1 com baseline definido.
- I-42: ExperimentRun completa só quando todas as combinações `variant × dataset_item` foram avaliadas.

### 2.6 Feedback
```
HumanFeedback
  id: ULID
  trace_id: FK
  source: enum(end_user, reviewer)
  thumbs: enum(up, down, neutral)?
  rating: int?  -- 1..5
  comment: text?
  tags: array<str>
  corrected_response: text?
  user_ref: str?
  reviewer_id: FK<User>?
  created_at
```

**Invariantes:**
- I-50: Pelo menos um de `thumbs`, `rating`, `comment` deve estar presente.
- I-51: `reviewer_id` é obrigatório se `source=reviewer`.

### 2.7 Datasets / Export
```
ExportJob
  id: ULID
  project_id: FK
  requested_by: FK<User>
  filters: jsonb
  format: enum(jsonl_chat, jsonl_dpo, csv)
  status: enum(queued, running, ready, error, expired)
  url: str?
  expires_at: datetime?
  row_count: int?
  size_bytes: int?
  created_at, completed_at
```

### 2.8 Billing
```
Plan (catálogo)
  id: str  -- "free", "pro", "team"
  monthly_traces_limit: int
  monthly_evals_limit: int
  retention_days: int
  price_usd: decimal

Subscription
  organization_id: FK (PK)
  plan_id: FK
  started_at, current_period_end, canceled_at?
  stripe_customer_id: str?  -- nullable no MVP

UsageCounter
  organization_id: FK
  period: str  -- "2026-04"
  traces_count: int
  evals_count: int
  judge_cost_usd: decimal
  storage_bytes: int
  PRIMARY KEY (organization_id, period)
```

## 3. Eventos de domínio (lógicos)

Eventos não são publicados para fora no MVP, mas o código emite-os internamente para acoplar lógica desacoplada (auto-eval, métricas, audit log).

| Evento | Produzido por | Consumido por |
|---|---|---|
| `trace.ingested` | TracingService | EvalService (auto-eval), UsageCounter |
| `evaluation.completed` | EvalService | dashboards (cache invalidation), drift detector (Futuro) |
| `feedback.received` | FeedbackService | UsageCounter, dataset builder |
| `experiment.completed` | ExperimentService | webhooks (Futuro), Slack notifier (Futuro) |
| `apikey.revoked` | AccessService | AuditLog, cache de keys |

Implementação MVP: in-process pub/sub (lista de handlers). Bus externo (Redis Streams, NATS) é Futuro.

## 4. Regras de negócio cross-context

1. **Auto-eval em ingestion:** se Project tem `auto_eval_rubrics: [...]`, cada trace ingerido dispara `EvalService.run(trace_id, rubric_id)` para cada rubric configurada.
2. **Quota enforcement:** ao ingerir trace, verificar `UsageCounter.traces_count + 1 ≤ Plan.monthly_traces_limit`. Se exceder, retornar 402 (Payment Required) ou 429 conforme política.
3. **Retention:** job diário deleta traces com `created_at < now() - retention_days * Project.retention_days`. Hard delete no MVP; soft delete em Futuro.
4. **Custo de eval atribuído à org dona do projeto** — somado ao `UsageCounter.judge_cost_usd`.
5. **Feedback negativo** com `score < 0.3` em rubrica + thumbs down marca trace como `flagged_for_review`.

## 5. Identidade & geração de IDs

- Todos os IDs públicos são **ULID** (26 chars, ordenáveis lexicograficamente por tempo).
- Prefixos sugeridos para legibilidade humana (mas o ID na DB é só ULID puro):
  - `org_*`, `proj_*`, `key_*`, `tr_*`, `sp_*`, `ev_*`, `rub_*`, `pr_*`, `ds_*`, `exp_*`, `fb_*`.

## 6. Pseudo-código das principais regras

```python
# Auto-eval em ingestion
async def on_trace_ingested(trace: Trace):
    project = await projects.get(trace.project_id)
    for rubric_slug in project.auto_eval_rubrics:
        rubric = await rubrics.get_by_slug(project.id, rubric_slug)
        await eval_service.schedule_run(trace.id, rubric.id, rubric.current_version)

# Quota check
def can_ingest(org: Organization, count: int) -> bool:
    plan = org.subscription.plan
    counter = usage.get_or_create(org.id, current_period())
    return counter.traces_count + count <= plan.monthly_traces_limit

# Score aggregation
def aggregate_scores(scores: list[EvaluationScore], method: str, weights: dict) -> float:
    if method == "weighted_mean":
        total_w = sum(weights.values())
        return sum(s.score * weights[s.evaluator_id] for s in scores) / total_w
    if method == "min":
        return min(s.score for s in scores)
    raise NotImplementedError
```
