# 20 - Implementation Task Breakdown

Breakdown operacional do EvalOps Studio. O foco aqui e execucao: ordem,
arquivos provaveis, testes obrigatorios e aceite por bloco.

## 1. Estrutura recomendada

```txt
apps/
  api/
    app/
      api/
      domain/
      infra/
      schemas/
      workers/
      cli/
      observability/
    tests/
  web/
    app/
    components/
    lib/
    tests/
packages/
  sdk-python/
    evalops/
    tests/
docs/
```

## 2. Fase 0 - Foundation

### 2.1 Repo and tooling

Tarefas:
- definir mono-repo;
- criar configs de Python, Node, lint e test;
- criar Docker Compose;
- subir CI minima.

Arquivos provaveis:
- `pyproject.toml`
- `apps/api/pyproject.toml`
- `apps/web/package.json`
- `docker-compose.yml`
- `.github/workflows/ci.yml`
- `.env.example`

Aceite:
- compose sobe;
- CI passa;
- build da web e import da API/SDK funcionam.

Testes obrigatorios:
- smoke de build;
- smoke de import.

### 2.2 Auth spike

Tarefas:
- provar Auth.js v5 com magic link + GitHub em preview;
- definir fluxo BFF -> FastAPI com JWT curto.

Arquivos provaveis:
- `apps/web/auth.ts`
- `apps/web/app/api/auth/[...nextauth]/route.ts`
- `apps/api/app/infra/auth/`

Aceite:
- login real funciona em preview.

Testes obrigatorios:
- login success path;
- callback invalido.

## 3. Fase 1 - Identity, org, project, keys

### 3.1 Backend identity/access

Tarefas:
- migrations de identity/access;
- services de org default/project/api key;
- hashing argon2id + prefix parsing;
- revogacao e scopes MVP.

Arquivos provaveis:
- `apps/api/alembic/versions/*_identity_access.py`
- `apps/api/app/domain/services/access_service.py`
- `apps/api/app/infra/auth/api_keys.py`
- `apps/api/app/api/routes/projects.py`
- `apps/api/app/api/routes/api_keys.py`

Aceite:
- usuario autenticado cria projeto e key;
- key revogada para de acessar API.

Testes obrigatorios:
- create project happy path;
- key stored hashed only;
- revoke key invalidates requests;
- cross-org access denied.

### 3.2 Frontend onboarding

Tarefas:
- login/onboarding/projects/api-keys pages;
- create key modal com one-time reveal.

Arquivos provaveis:
- `apps/web/app/login/page.tsx`
- `apps/web/app/onboarding/page.tsx`
- `apps/web/app/o/[org]/page.tsx`
- `apps/web/app/o/[org]/p/[project]/api-keys/page.tsx`

Aceite:
- usuario novo chega ate a tela da key em um fluxo.

Testes obrigatorios:
- onboarding flow;
- create project form.

## 4. Fase 2 - Tracing core

### 4.1 Data model and ingestion

Tarefas:
- migrations `traces`, `spans`, `events`;
- parser do payload batch;
- idempotencia;
- calculo de duration/tokens/cost;
- persistencia transacional com erros por item;
- listagem e detalhe de traces.

Arquivos provaveis:
- `apps/api/alembic/versions/*_tracing.py`
- `apps/api/app/schemas/traces.py`
- `apps/api/app/domain/services/ingestion_service.py`
- `apps/api/app/infra/db/repositories/traces_repo.py`
- `apps/api/app/api/routes/traces.py`
- `apps/api/app/infra/llm/pricing.py`

Aceite:
- trace detail traz spans e events corretamente;
- casos com tool call e fallback persistem corretamente.

Testes obrigatorios:
- ingest happy path;
- idempotencia;
- partial item errors;
- totals match spans;
- delete trace.

### 4.2 SDK Python v0.1

Tarefas:
- `init`, decorator, context manager;
- uploader bounded queue;
- retry/backoff;
- disabled mode;
- helper `feedback`.

Arquivos provaveis:
- `packages/sdk-python/evalops/client.py`
- `packages/sdk-python/evalops/tracer.py`
- `packages/sdk-python/evalops/uploader.py`
- `packages/sdk-python/tests/`

Aceite:
- SDK envia traces reais em uma app de exemplo.

Testes obrigatorios:
- no-op when disabled;
- 5xx nao propaga;
- flush interval/max_batch;
- stress basico de concorrencia.

## 5. Fase 3 - Trace dashboard

### 5.1 Read-side metrics

Tarefas:
- queries agregadas para overview;
- filtros e cursor na listagem.

Arquivos provaveis:
- `apps/api/app/domain/services/analytics_service.py`
- `apps/api/app/api/routes/analytics.py`

Aceite:
- overview retorna KPIs coerentes.

Testes obrigatorios:
- date/model/status filters;
- cursor pagination stable.

### 5.2 Web trace UX

Tarefas:
- overview, traces list, trace detail;
- span tree viewer;
- charts basicos;
- URL-persistent filters.

Arquivos provaveis:
- `apps/web/app/o/[org]/p/[project]/page.tsx`
- `apps/web/app/o/[org]/p/[project]/traces/page.tsx`
- `apps/web/app/o/[org]/p/[project]/traces/[trace]/page.tsx`
- `apps/web/components/trace-tree-view.tsx`

Aceite:
- dashboard ja e util antes de eval.

Testes obrigatorios:
- render empty state;
- filters persist in URL;
- trace detail handles nested spans.

## 6. Fase 4 - Rubrics and eval engine

### 6.1 Rubric management

Tarefas:
- migrations evaluation;
- parser/validator strict do YAML;
- push de nova versao;
- parsed spec persistido + evaluators normalizados.

Arquivos provaveis:
- `apps/api/alembic/versions/*_evaluation.py`
- `apps/api/app/domain/services/rubric_service.py`
- `apps/api/app/domain/rubrics/parser.py`
- `apps/api/app/api/routes/rubrics.py`

Aceite:
- invalid YAML retorna 422;
- versao nova e imutavel.

Testes obrigatorios:
- validator strict;
- version n+1.

### 6.2 Evaluators and run execution

Tarefas:
- implementar 7 evaluators MVP;
- `EvalService.run`;
- aggregate + auto-fail;
- endpoint sync + run detail.

Arquivos provaveis:
- `apps/api/app/domain/evaluators/`
- `apps/api/app/domain/services/eval_service.py`
- `apps/api/app/infra/llm/client.py`
- `apps/api/app/api/routes/evaluations.py`

Aceite:
- trace real avaliado manualmente com score persistido.

Testes obrigatorios:
- um teste por evaluator;
- weighted_mean/min/max;
- fail_fast and auto_fail;
- invalid judge JSON retry;
- budget exhausted.

## 7. Fase 5 - Prompts, datasets, experiments, CLI

### 7.1 Prompt and dataset primitives

Tarefas:
- migrations prompts/datasets;
- CRUD basico;
- resolver `prompt_version_ref`.

Arquivos provaveis:
- `apps/api/alembic/versions/*_prompts_datasets.py`
- `apps/api/app/domain/services/prompt_service.py`
- `apps/api/app/domain/services/dataset_service.py`

Aceite:
- prompt ref resolve de `slug@version`.

Testes obrigatorios:
- prompt version immutability;
- dataset item create/list.

### 7.2 Experiments and regression

Tarefas:
- migrations experiments;
- executor sync com concorrencia limitada;
- CLI `prompts push`, `rubrics push`, `experiment run`.

Arquivos provaveis:
- `apps/api/app/domain/services/experiment_service.py`
- `apps/api/app/api/routes/experiments.py`
- `apps/api/app/cli/main.py`

Aceite:
- regression suite manual bloqueia regressao real.

Testes obrigatorios:
- experiment com 2 variants;
- regression fail exit code;
- result summary with pass_rate/cost/avg_score.

## 8. Fase 6 - Feedback, export, quotas

### 8.1 Feedback loop

Tarefas:
- migration `human_feedback`;
- create/list feedback endpoints;
- trace detail feedback panel.

Arquivos provaveis:
- `apps/api/alembic/versions/*_feedback_export_usage.py`
- `apps/api/app/domain/services/feedback_service.py`
- `apps/api/app/api/routes/feedback.py`
- `apps/web/components/feedback-panel.tsx`

Aceite:
- feedback aparece no trace detail.

Testes obrigatorios:
- feedback validation;
- feedback list in trace.

### 8.2 Export and usage counters

Tarefas:
- export jobs + JSONL serializer;
- usage counters update;
- mock plans/subscriptions;
- audit log records.

Arquivos provaveis:
- `apps/api/app/domain/services/export_service.py`
- `apps/api/app/domain/services/billing_service.py`
- `apps/api/app/api/routes/exports.py`
- `apps/api/app/api/routes/usage.py`

Aceite:
- corrected response consegue virar export util.

Testes obrigatorios:
- JSONL export valid;
- filters subset;
- usage increments;
- quota exceeded error.

## 9. Fase 7 - MVP release prep

Tarefas:
- hardening de UX;
- README/SDK docs;
- hosted deploy;
- one real portfolio integration;
- video/demo assets.

Arquivos provaveis:
- `README.md`
- `packages/sdk-python/README.md`
- deploy configs

Aceite:
- checklist do MVP completo e apresentavel.

Testes obrigatorios:
- hosted smoke;
- one E2E happy path;
- one real integration smoke.

## 10. Fase 1.1 - Async hardening

Tarefas:
- Arq worker settings and tasks;
- async eval/export endpoints;
- Redis token bucket;
- judge cache.

Arquivos provaveis:
- `apps/api/app/workers/worker_settings.py`
- `apps/api/app/workers/tasks.py`
- `apps/api/app/infra/queue/arq_adapter.py`

Aceite:
- queued eval path funcional;
- ingestion nao degrada com auto-eval ligado.

Testes obrigatorios:
- queued eval path;
- duplicate run dedup;
- retry semantics.

## 11. Sequencia que nao deve ser violada

1. Auth/tenancy antes de traces.
2. Traces antes de dashboard detalhado.
3. Trace detail antes de eval UI.
4. Eval manual antes de auto-eval.
5. Datasets antes de experiments.
6. MVP sync completo antes de Arq.
