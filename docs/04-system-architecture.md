# 04 — System Architecture

## 1. Visão macro

```
                         ┌──────────────────────────────┐
                         │  Apps instrumentados (cliente)│
                         │  DocOps · ImobiliarIA · Aurora│
                         │   ┌──────────────────────┐    │
                         │   │  evalops-python SDK  │    │
                         │   │   (batch + retry)    │    │
                         │   └─────────┬────────────┘    │
                         └─────────────┼─────────────────┘
                                       │ HTTPS (API key)
                                       ▼
   ┌─────────────────────────────────────────────────────────────┐
   │                  EvalOps Studio — Backend (FastAPI)          │
   │                                                              │
   │  ┌──────────────┐  ┌───────────────┐  ┌─────────────────┐    │
   │  │ Ingestion    │  │ Public API    │  │ Admin API       │    │
   │  │  /v1/traces  │  │ projects,keys │  │ orgs, billing   │    │
   │  └──────┬───────┘  │ rubrics,exps  │  └─────────────────┘    │
   │         │          └───────┬───────┘                         │
   │         │ enqueue          │                                 │
   │         ▼                  ▼                                 │
   │  ┌────────────────────────────────────────────────────┐      │
   │  │  Domain services (Python)                          │      │
   │  │  TracingService · EvalService · ExperimentService  │      │
   │  │  ExportService · BillingService                    │      │
   │  └────────────┬───────────────────────────┬───────────┘      │
   │               ▼                           ▼                  │
   │     ┌──────────────────┐         ┌──────────────────┐        │
   │     │ PostgreSQL 16    │         │ Redis (Upstash)  │        │
   │     │ (Neon)           │         │ queue + cache    │        │
   │     └──────────────────┘         └─────────┬────────┘        │
   │                                            │                 │
   │                                  ┌─────────▼────────────┐    │
   │                                  │ Eval Worker (Arq)    │    │
   │                                  │ — Fase 1.1 —         │    │
   │                                  │ chama LLM judges     │    │
   │                                  └──────────┬───────────┘    │
   └─────────────────────────────────────────────┼────────────────┘
                                                 │
                                ┌────────────────┴────────────────┐
                                ▼                ▼                ▼
                            OpenAI          Gemini             Groq
                                                                   
                          (todos via litellm)

   ┌──────────────────────────────────────┐
   │  Frontend (Next.js 15 — Vercel)      │
   │  Dashboard, Auth, Settings           │
   │  Server Actions → Public API         │
   └──────────────────────────────────────┘
```

## 2. Componentes

### 2.1 SDK Python (`evalops-python`)
- Pacote `evalops`. Sem deps pesadas (`httpx`, `pydantic`, `structlog`).
- Threading model: `BackgroundUploader` em thread daemon, fila in-memory bounded (default 1024); drop com warning quando cheia.
- Fail-safe: nenhum erro propaga. Modo `disabled=True` para dev local.
- Auto-instrument opt-in: `evalops.instrument_openai()`, `instrument_anthropic()`, `instrument_gemini()` — patcha o cliente e emite span por chamada.
- Versão alvo MVP: `0.1.x`.

### 2.2 Backend FastAPI

Camadas (clean architecture lite):

```
app/
  api/                   # FastAPI routers (HTTP shape only)
  domain/                # business logic puro (zero deps de framework)
    entities/            # Pydantic models domínio
    services/            # casos de uso
  infra/                 # adapters concretos
    db/                  # SQLAlchemy + Alembic
    queue/               # Arq (Fase 1.1) ou stub sync
    llm/                 # litellm wrappers + providers
    storage/             # S3-compatible para exports
    auth/                # JWT verify, API key check
  schemas/               # Pydantic I/O (request/response)
  workers/               # Arq tasks
  cli/                   # Typer CLI (`evalops`)
  observability/         # logs, metrics, tracing internos
```

Por que esta separação: facilita testar `domain/` sem subir DB/Redis e permite trocar Arq por outra fila no futuro sem mexer em services.

### 2.3 Workers (Fase 1.1)
- Stack: **Arq** (async-native, Redis-based). Alternativa considerada: Celery (rejeitada — sync-first, mais peso). RQ (rejeitada — sync-first).
- Tasks principais:
  - `eval_run(trace_id, rubric_id, version)` — roda evaluators e persiste `evaluation_run`.
  - `experiment_run(experiment_id)` — fan-out de N execuções de evaluators.
  - `dataset_export(export_id, filters)` — query + serialização JSONL → upload.
- Retry: exponencial (3 tentativas), DLQ em Redis para inspeção.

### 2.4 Frontend Next.js
- App Router; mistura Server Components (listagens, detalhes, charts) e Client Components (filtros, formulários).
- Auth.js v5: sessão em cookie HttpOnly, JWT short-lived (15 min) + refresh em DB.
- Comunicação com backend via fetch direto (server-side, com cookie de sessão → JWT) ou via Server Actions encapsuladas.
- shadcn/ui + Tailwind. Charts: Recharts (suficiente) ou Tremor (mais rápido para dashboards).

### 2.5 Banco de dados
- **PostgreSQL 16** (Neon — serverless, branching, free tier generoso para dev).
- Particionamento de `trace` e `span` por `created_at` (monthly) é **Fase 2** — no MVP, índices bem feitos resolvem.
- Extensions: `pgcrypto` (hash IDs se necessário), `pg_trgm` (busca textual em prompts).

### 2.6 Cache / Fila
- **Upstash Redis** (serverless, free tier OK).
- Usos: fila Arq (Fase 1.1), rate limit (token bucket), cache de `pricing` e `rubric` carregados.

### 2.7 Storage
- Exports e arquivos grandes em **S3-compatible** (Cloudflare R2 — sem egress fee).
- URLs pré-assinadas com TTL 24h.

### 2.8 LLM providers
- Abstração via **`litellm`**. Justificativa: 1 lib cobre OpenAI/Anthropic/Gemini/Groq/Ollama, com normalização de cost/usage.
- Pricing table local em `app/infra/llm/pricing.py` (validada contra preços oficiais a cada release).

## 3. Fluxos críticos

### 3.1 Ingestion de trace
```
SDK ──[POST /v1/traces (batch)]──▶ Ingestion endpoint
                                        │
                                        ├── valida API key (cache 60s)
                                        ├── valida rate limit
                                        ├── valida payload (Pydantic)
                                        ├── enriquece (cost = pricing × tokens)
                                        ├── INSERT batch (trace + spans + events)
                                        ├── enqueue auto-eval jobs (se Fase 1.1)
                                        └── 202 Accepted { ingested: N, ids: [...] }
```
- Idempotência: `client_trace_id` + `project_id` é UNIQUE.
- Erros de validação de itens individuais não rejeitam o batch — retorno parcial.

### 3.2 Eval (síncrono no MVP)
```
POST /v1/evaluations/run { trace_id, rubric_id }
   │
   ├── carrega trace + rubric_version
   ├── para cada evaluator da rubric:
   │     ├── monta input
   │     ├── executa (regex/llm_judge/...)
   │     ├── coleta score, cost, latency
   ├── agrega (mean/min/weighted)
   ├── persiste evaluation_run + evaluation_score (1:N)
   └── retorna { run_id, score, passed }
```
> Fase 1.1: substituir execução inline por `enqueue` + worker.

### 3.3 Experiment / Regression
```
POST /v1/experiments/{id}/run
   │
   ├── valida dataset existe
   ├── cria experiment_run
   ├── para cada (variant × dataset_item):
   │     ├── chama LLM com prompt_version + model do variant
   │     ├── persiste como trace temporário (tag=experiment)
   │     ├── roda rubrica
   ├── agrega métricas por variant
   ├── compara com baseline
   └── retorna relatório + URL
```

### 3.4 Export
```
POST /v1/datasets/export { filters }
   │
   ├── cria export_job (status=queued)
   └── responde { export_id, status_url }
       
   Worker:
   ├── streaming query (server-side cursor) sobre filtros
   ├── serializa JSONL chat-format
   ├── upload para R2
   ├── update export_job (status=ready, url, expires_at)
   └── (Futuro) webhook
```

## 4. Multi-tenancy

- Toda query passa por `organization_id`.
- Enforced no **repository layer** (não em endpoint, não em SQL cru): `ProjectRepo.get_by_id(project_id, *, org_id)` exige org_id.
- PostgreSQL **Row-Level Security** habilitado nas tabelas de dados de cliente (`trace`, `span`, `evaluation_run`...) com policy `current_setting('app.org_id')::uuid = organization_id`. App seta `SET LOCAL app.org_id = ...` no início de cada transaction.
- API keys são scoped por projeto, e projeto pertence a 1 org → org_id é derivado da key.

## 5. Modelo de erros

Toda resposta de erro da API tem shape fixo:
```json
{
  "error": {
    "code": "rate_limit_exceeded",
    "message": "Rate limit of 60 req/min exceeded",
    "request_id": "req_01HX...",
    "docs_url": "https://docs.evalops.studio/errors/rate_limit_exceeded"
  }
}
```
Códigos estáveis (ver `07-api-spec.md` §Errors).

## 6. Idempotência & deduplicação

| Operação | Chave de idempotência |
|---|---|
| `POST /v1/traces` | `(project_id, client_trace_id)` |
| `POST /v1/evaluations/run` | `(trace_id, rubric_id, rubric_version)` — return existing se já rodado |
| `POST /v1/experiments/{id}/run` | `experiment_id` + body hash → 1 run ativo por vez |

## 7. Decisões arquiteturais que precisam de ADR

- ADR-0001 — Tech stack
- ADR-0002 — Síncrono vs assíncrono no MVP
- ADR-0003 — Estratégia de avaliação (LLM-as-judge vs heurísticas)
- ADR-0004 — Modelo de dados de tracing (trace+span+event vs flat events)
- ADR-0005 — Auth & API keys

## 8. Não-objetivos arquiteturais (no MVP)

- Multi-region failover.
- Streaming de traces (WebSocket/SSE) — ingestion é REST batch.
- ACID forte cross-tabela com sagas — usamos transações Postgres normais.
- Schema registry externo (Protobuf/Avro) — JSON com Pydantic basta.
