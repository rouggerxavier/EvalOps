# 06 — Data Model (PostgreSQL)

Tradução do [domain model](05-domain-model.md) para schema concreto. SQL apresentado em estilo Postgres 16. Migrações via Alembic.

## 1. Convenções

- IDs `BYTEA(16)` armazenando ULID em binário, com `text_id` `GENERATED ALWAYS AS` (Crockford base32) — ou simplesmente `TEXT` de 26 chars (mais simples; default no MVP). **Decisão MVP: TEXT(26).**
- `created_at`, `updated_at` em `TIMESTAMPTZ` com default `now()`.
- Campos JSON usam `JSONB`.
- Money: `NUMERIC(12,6)` para custos USD.
- Soft delete: coluna `archived_at` (não `deleted_at`) onde aplicável; default é hard delete.
- FKs com `ON DELETE` explícito (`CASCADE` para children de agregado, `RESTRICT` para refs cross-context).

## 2. Schema SQL

### 2.1 Identity & Access

```sql
CREATE TABLE users (
  id              TEXT PRIMARY KEY,
  email           CITEXT NOT NULL UNIQUE,
  name            TEXT NOT NULL,
  email_verified_at TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE organizations (
  id              TEXT PRIMARY KEY,
  name            TEXT NOT NULL,
  slug            TEXT NOT NULL UNIQUE,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE memberships (
  user_id         TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  role            TEXT NOT NULL CHECK (role IN ('owner','admin','member','viewer')),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, organization_id)
);
CREATE INDEX idx_memberships_org ON memberships(organization_id);

CREATE TABLE projects (
  id                  TEXT PRIMARY KEY,
  organization_id     TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  name                TEXT NOT NULL,
  slug                TEXT NOT NULL,
  description         TEXT,
  default_environment TEXT NOT NULL DEFAULT 'prod' CHECK (default_environment IN ('dev','staging','prod')),
  retention_days      INT  NOT NULL DEFAULT 90,
  redaction_enabled   BOOLEAN NOT NULL DEFAULT false,
  auto_eval_rubrics   JSONB NOT NULL DEFAULT '[]'::jsonb, -- ["rubric-slug-1", ...]
  archived_at         TIMESTAMPTZ,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (organization_id, slug)
);

CREATE TABLE api_keys (
  id              TEXT PRIMARY KEY,
  project_id      TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  prefix          TEXT NOT NULL,           -- "evk_live_a1b2"
  hash            TEXT NOT NULL,           -- argon2id
  name            TEXT NOT NULL,
  environment     TEXT NOT NULL,
  scopes          TEXT[] NOT NULL DEFAULT ARRAY['ingest','read'],
  rate_limit_per_minute INT NOT NULL DEFAULT 60,
  last_used_at    TIMESTAMPTZ,
  revoked_at      TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_api_keys_project ON api_keys(project_id) WHERE revoked_at IS NULL;
CREATE INDEX idx_api_keys_prefix  ON api_keys(prefix);
```

### 2.2 Tracing (hot path)

```sql
CREATE TABLE traces (
  id                  TEXT PRIMARY KEY,
  project_id          TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  organization_id     TEXT NOT NULL,            -- denormalized para RLS/queries
  client_trace_id     TEXT,
  name                TEXT NOT NULL,
  service             TEXT,
  environment         TEXT NOT NULL,
  status              TEXT NOT NULL CHECK (status IN ('ok','error','partial')),
  started_at          TIMESTAMPTZ NOT NULL,
  ended_at            TIMESTAMPTZ NOT NULL,
  duration_ms         INT NOT NULL,
  total_tokens_in     INT NOT NULL DEFAULT 0,
  total_tokens_out    INT NOT NULL DEFAULT 0,
  total_cost_usd      NUMERIC(12,6) NOT NULL DEFAULT 0,
  tags                JSONB NOT NULL DEFAULT '{}'::jsonb,
  user_ref            TEXT,
  metadata            JSONB NOT NULL DEFAULT '{}'::jsonb,
  redacted            BOOLEAN NOT NULL DEFAULT false,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX uq_traces_client_id  ON traces(project_id, client_trace_id) WHERE client_trace_id IS NOT NULL;
CREATE INDEX idx_traces_proj_time        ON traces(project_id, created_at DESC);
CREATE INDEX idx_traces_proj_status_time ON traces(project_id, status, created_at DESC);
CREATE INDEX idx_traces_user_ref         ON traces(project_id, user_ref) WHERE user_ref IS NOT NULL;
CREATE INDEX idx_traces_tags             ON traces USING GIN (tags);
CREATE INDEX idx_traces_name_trgm        ON traces USING GIN (name gin_trgm_ops);

CREATE TABLE spans (
  id                  TEXT PRIMARY KEY,
  trace_id            TEXT NOT NULL REFERENCES traces(id) ON DELETE CASCADE,
  parent_span_id      TEXT REFERENCES spans(id) ON DELETE CASCADE,
  type                TEXT NOT NULL CHECK (type IN ('llm_call','tool_call','retrieval','embedding','agent_step','chain')),
  name                TEXT NOT NULL,
  status              TEXT NOT NULL CHECK (status IN ('ok','error')),
  started_at          TIMESTAMPTZ NOT NULL,
  ended_at            TIMESTAMPTZ NOT NULL,
  duration_ms         INT NOT NULL,
  -- llm_call
  provider            TEXT,
  model               TEXT,
  prompt_version_id   TEXT REFERENCES prompt_versions(id) ON DELETE SET NULL,
  messages_in         JSONB,
  messages_out        JSONB,
  tools               JSONB,
  tokens_in           INT,
  tokens_out          INT,
  cost_usd            NUMERIC(12,6),
  fallback_from_span_id TEXT REFERENCES spans(id) ON DELETE SET NULL,
  -- generic
  input               JSONB,
  output              JSONB,
  error               JSONB,
  metadata            JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX idx_spans_trace ON spans(trace_id);
CREATE INDEX idx_spans_type  ON spans(trace_id, type);
CREATE INDEX idx_spans_model ON spans(model) WHERE model IS NOT NULL;

CREATE TABLE events (
  id          TEXT PRIMARY KEY,
  span_id     TEXT NOT NULL REFERENCES spans(id) ON DELETE CASCADE,
  type        TEXT NOT NULL,
  occurred_at TIMESTAMPTZ NOT NULL,
  payload     JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX idx_events_span ON events(span_id);
```

### 2.3 Evaluation

```sql
CREATE TABLE rubrics (
  id              TEXT PRIMARY KEY,
  project_id      TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  slug            TEXT NOT NULL,
  description     TEXT,
  current_version INT NOT NULL DEFAULT 1,
  threshold       NUMERIC(4,3) NOT NULL DEFAULT 0.7,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (project_id, slug)
);

CREATE TABLE rubric_versions (
  id              TEXT PRIMARY KEY,
  rubric_id       TEXT NOT NULL REFERENCES rubrics(id) ON DELETE CASCADE,
  version         INT NOT NULL,
  yaml_source     TEXT NOT NULL,
  parsed_spec     JSONB NOT NULL,
  created_by      TEXT NOT NULL REFERENCES users(id),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  archived_at     TIMESTAMPTZ,
  UNIQUE (rubric_id, version)
);

CREATE TABLE evaluators (
  id              TEXT PRIMARY KEY,
  rubric_version_id TEXT NOT NULL REFERENCES rubric_versions(id) ON DELETE CASCADE,
  type            TEXT NOT NULL,
  config          JSONB NOT NULL,
  weight          NUMERIC(6,3) NOT NULL DEFAULT 1.0,
  fail_fast       BOOLEAN NOT NULL DEFAULT false,
  ord             INT NOT NULL DEFAULT 0
);
CREATE INDEX idx_evaluators_rubric ON evaluators(rubric_version_id, ord);

CREATE TABLE evaluation_runs (
  id                TEXT PRIMARY KEY,
  project_id        TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  trace_id          TEXT NOT NULL REFERENCES traces(id) ON DELETE CASCADE,
  rubric_id         TEXT NOT NULL REFERENCES rubrics(id) ON DELETE RESTRICT,
  rubric_version    INT NOT NULL,
  triggered_by      TEXT NOT NULL CHECK (triggered_by IN ('api','auto','schedule','experiment')),
  status            TEXT NOT NULL CHECK (status IN ('queued','running','completed','error')),
  aggregate_score   NUMERIC(6,4),
  passed            BOOLEAN,
  cost_usd          NUMERIC(12,6) NOT NULL DEFAULT 0,
  latency_ms        INT,
  started_at        TIMESTAMPTZ,
  completed_at      TIMESTAMPTZ,
  error             JSONB,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (trace_id, rubric_id, rubric_version)
);
CREATE INDEX idx_eval_runs_proj_time ON evaluation_runs(project_id, created_at DESC);
CREATE INDEX idx_eval_runs_status    ON evaluation_runs(status) WHERE status IN ('queued','running');

CREATE TABLE evaluation_scores (
  id              TEXT PRIMARY KEY,
  run_id          TEXT NOT NULL REFERENCES evaluation_runs(id) ON DELETE CASCADE,
  evaluator_id    TEXT NOT NULL REFERENCES evaluators(id) ON DELETE RESTRICT,
  score           NUMERIC(6,4) NOT NULL,
  passed          BOOLEAN NOT NULL,
  reasoning       TEXT,
  raw_output      JSONB,
  cost_usd        NUMERIC(12,6) NOT NULL DEFAULT 0,
  latency_ms      INT NOT NULL DEFAULT 0
);
CREATE INDEX idx_eval_scores_run ON evaluation_scores(run_id);
```

### 2.4 Versioning (prompts, datasets, experiments)

```sql
CREATE TABLE prompts (
  id              TEXT PRIMARY KEY,
  project_id      TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  slug            TEXT NOT NULL,
  current_version INT NOT NULL DEFAULT 1,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (project_id, slug)
);

CREATE TABLE prompt_versions (
  id              TEXT PRIMARY KEY,
  prompt_id       TEXT NOT NULL REFERENCES prompts(id) ON DELETE CASCADE,
  version         INT NOT NULL,
  template        TEXT NOT NULL,
  variables       JSONB NOT NULL DEFAULT '{}'::jsonb,
  metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
  changelog       TEXT,
  created_by      TEXT NOT NULL REFERENCES users(id),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (prompt_id, version)
);

CREATE TABLE datasets (
  id              TEXT PRIMARY KEY,
  project_id      TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  slug            TEXT NOT NULL,
  description     TEXT,
  source          TEXT NOT NULL CHECK (source IN ('manual','from_traces','uploaded')),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (project_id, slug)
);

CREATE TABLE dataset_items (
  id              TEXT PRIMARY KEY,
  dataset_id      TEXT NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
  input           JSONB NOT NULL,
  expected_output JSONB,
  metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
  source_trace_id TEXT REFERENCES traces(id) ON DELETE SET NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_dataset_items_ds ON dataset_items(dataset_id);

CREATE TABLE experiments (
  id              TEXT PRIMARY KEY,
  project_id      TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  name            TEXT NOT NULL,
  dataset_id      TEXT NOT NULL REFERENCES datasets(id) ON DELETE RESTRICT,
  rubric_id       TEXT NOT NULL REFERENCES rubrics(id) ON DELETE RESTRICT,
  variants        JSONB NOT NULL,
  pass_criteria   JSONB NOT NULL DEFAULT '{}'::jsonb,
  baseline_variant TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE experiment_runs (
  id              TEXT PRIMARY KEY,
  experiment_id   TEXT NOT NULL REFERENCES experiments(id) ON DELETE CASCADE,
  status          TEXT NOT NULL CHECK (status IN ('queued','running','completed','error')),
  results         JSONB,
  passed          BOOLEAN,
  triggered_by    TEXT NOT NULL,
  total_cost_usd  NUMERIC(12,6) NOT NULL DEFAULT 0,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at    TIMESTAMPTZ
);
CREATE INDEX idx_exp_runs_exp_time ON experiment_runs(experiment_id, created_at DESC);
```

### 2.5 Feedback & Datasets

```sql
CREATE TABLE human_feedback (
  id                  TEXT PRIMARY KEY,
  trace_id            TEXT NOT NULL REFERENCES traces(id) ON DELETE CASCADE,
  source              TEXT NOT NULL CHECK (source IN ('end_user','reviewer')),
  thumbs              TEXT CHECK (thumbs IN ('up','down','neutral')),
  rating              INT  CHECK (rating BETWEEN 1 AND 5),
  comment             TEXT,
  tags                TEXT[] NOT NULL DEFAULT '{}',
  corrected_response  TEXT,
  user_ref            TEXT,
  reviewer_id         TEXT REFERENCES users(id) ON DELETE SET NULL,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_feedback_trace ON human_feedback(trace_id);
CREATE INDEX idx_feedback_thumbs ON human_feedback(trace_id, thumbs);

CREATE TABLE export_jobs (
  id              TEXT PRIMARY KEY,
  project_id      TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  requested_by    TEXT NOT NULL REFERENCES users(id),
  filters         JSONB NOT NULL,
  format          TEXT NOT NULL CHECK (format IN ('jsonl_chat','jsonl_dpo','csv')),
  status          TEXT NOT NULL CHECK (status IN ('queued','running','ready','error','expired')),
  url             TEXT,
  expires_at      TIMESTAMPTZ,
  row_count       BIGINT,
  size_bytes      BIGINT,
  error           JSONB,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at    TIMESTAMPTZ
);
CREATE INDEX idx_export_jobs_proj_status ON export_jobs(project_id, status);
```

### 2.6 Billing

```sql
CREATE TABLE plans (
  id                      TEXT PRIMARY KEY,  -- 'free','pro','team'
  name                    TEXT NOT NULL,
  monthly_traces_limit    INT NOT NULL,
  monthly_evals_limit     INT NOT NULL,
  retention_days          INT NOT NULL,
  price_usd               NUMERIC(8,2) NOT NULL DEFAULT 0
);

CREATE TABLE subscriptions (
  organization_id     TEXT PRIMARY KEY REFERENCES organizations(id) ON DELETE CASCADE,
  plan_id             TEXT NOT NULL REFERENCES plans(id),
  started_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  current_period_end  TIMESTAMPTZ NOT NULL,
  canceled_at         TIMESTAMPTZ,
  stripe_customer_id  TEXT
);

CREATE TABLE usage_counters (
  organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  period          TEXT NOT NULL,           -- 'YYYY-MM'
  traces_count    BIGINT NOT NULL DEFAULT 0,
  evals_count     BIGINT NOT NULL DEFAULT 0,
  judge_cost_usd  NUMERIC(12,6) NOT NULL DEFAULT 0,
  storage_bytes   BIGINT NOT NULL DEFAULT 0,
  PRIMARY KEY (organization_id, period)
);
```

### 2.7 Audit log

```sql
CREATE TABLE audit_logs (
  id              TEXT PRIMARY KEY,
  organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  actor_user_id   TEXT REFERENCES users(id) ON DELETE SET NULL,
  actor_api_key_id TEXT REFERENCES api_keys(id) ON DELETE SET NULL,
  action          TEXT NOT NULL,            -- "api_key.revoked"
  target_type     TEXT,
  target_id       TEXT,
  metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
  ip              INET,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_audit_org_time ON audit_logs(organization_id, created_at DESC);
```

## 3. Row-Level Security (RLS)

Habilitar em **todas** as tabelas que carregam `organization_id`. Policy padrão:

```sql
ALTER TABLE traces ENABLE ROW LEVEL SECURITY;

CREATE POLICY traces_org_isolation ON traces
  USING (organization_id = current_setting('app.org_id', true));
```

Aplicar mesmo padrão para: `projects`, `api_keys` (via join → trigger), `evaluation_runs`, `evaluation_scores`, `experiments`, `experiment_runs`, `prompts`, `datasets`, `human_feedback`, `export_jobs`.

> Service code seta `SET LOCAL app.org_id = '{org_id}'` no início de cada transação. **Pool de conexões deve resetar** isso a cada checkout.

## 4. Particionamento (Futuro)

Quando `traces` passar de ~5M linhas:

```sql
-- Convert traces to partitioned by RANGE (created_at) monthly.
-- spans, events, evaluation_runs seguem o mesmo padrão.
```

No MVP, índices em `(project_id, created_at DESC)` cobrem queries comuns sem necessidade de particionar.

## 5. Migrations seed

Seed inicial:
- 3 plans: `free` (10k traces, 1k evals, 30d), `pro` (100k traces, 10k evals, 90d, $29/mo), `team` (1M, 100k, 365d, $199/mo).
- Pricing table de modelos: `gpt-4o-mini`, `gpt-4.1`, `gemini-2.5-flash`, `gemini-2.5-pro`, `llama-3.3-70b@groq`, `claude-haiku-4-5`.
- Rubric exemplo: `default-llm-helpfulness` com 1 evaluator `llm_judge`.

## 6. Estimativa de tamanho (MVP)

Premissa: 1.000 traces/dia, 5 spans cada, 1 eval por trace.

- `traces`: 30k/mês × ~2KB = 60 MB/mês.
- `spans`: 150k/mês × ~3KB = 450 MB/mês.
- `events`: insignificante.
- Após 12 meses: ~6 GB. Postgres comporta facilmente em planos starter.

## 7. Backup & retention de DB

- Backup automático Neon (point-in-time recovery 7 dias no plano starter).
- Logical backup mensal exportado para R2 (cold storage).
- **Não** logar conteúdo de prompts em logs do app (NFR-33).
