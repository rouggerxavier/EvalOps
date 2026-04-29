# ADR-0001 — Tech Stack

- **Status:** Accepted
- **Data:** 2026-04-29
- **Decisor:** Autor (João)
- **Contexto:** decisão fundadora; informa todas as outras.

## Contexto

EvalOps Studio precisa de stack que suporte:
- API HTTP performática para ingestion (potencialmente alta vazão).
- Workers assíncronos para evaluators LLM-as-judge (latência alta).
- Frontend de dashboard rico, com gráficos e drill-down.
- Multi-tenant desde o início.
- Boa DX (autor solo, ~20h/semana).
- Coerência razoável com o restante do portfólio do autor (DocOps, Aurora — ambos Python).

## Opções consideradas

### Backend

| Opção | Prós | Contras |
|---|---|---|
| **FastAPI + Python 3.12** ✅ | Eco LLMOps maduro (`litellm`, `pydantic-ai`, `instructor`); SDK Python natural; mesma linguagem dos projetos do autor; tipagem com Pydantic | Workers async menos triviais que Node; pip vs uv vs poetry — fragmentação |
| Node + TS (Nest/Fastify) | Tipagem ponta-a-ponta com frontend; ecossistema bom | Eco LLMOps menor; SDK Python ainda seria escrito separado; menos coerência com portfólio |
| Híbrido FastAPI + Next.js BFF | Mantém Python para core | Complexidade extra de manter 2 backends |

### Frontend

| Opção | Prós | Contras |
|---|---|---|
| **Next.js 15 App Router + Tailwind + shadcn/ui** ✅ | Padrão de mercado SaaS 2026; server components reduzem boilerplate; shadcn dá visual profissional; Auth.js integra | Curva server/client components; vendor lock-in suave em Vercel |
| Vite SPA pura | Mais simples | Menos "wow"; SEO de landing fica externo |
| Streamlit | Rápido para POCs | Inadequado para dashboard de observabilidade interativo |

### Banco

| Opção | Decisão |
|---|---|
| **PostgreSQL 16 (Neon)** ✅ | Relacional + JSONB cobre tudo no MVP; branching de DB acelera dev |
| ClickHouse | Excelente para traces em volume | Adia para Fase 3 |
| MongoDB | Schema flexível | Perde joins úteis para queries de relatório |

### Fila / cache

| Opção | Decisão |
|---|---|
| **Redis (Upstash) + Arq** ✅ (Fase 1.1) | Redis é onipresente; Arq é async-native; Upstash REST simplifica edge se preciso |
| Celery | Maturidade | Sync-first; mais peso |
| RQ | Simples | Sync-first |
| Cloud Tasks / SQS | Gerenciado | Vendor lock-in alto |
| BullMQ (Node) | Excelente | Mas backend é Python |

### LLM abstraction

| Opção | Decisão |
|---|---|
| **`litellm`** ✅ | 1 lib cobre OpenAI/Anthropic/Gemini/Groq/Ollama; normalização de cost; mainstream |
| Direto com SDKs | Mais controle | Multiplica código por provider |
| `pydantic-ai` | Tipagem rica | Foco em agentes, não simples chamada |

### Auth

| Opção | Decisão |
|---|---|
| **Auth.js v5 (NextAuth)** ✅ | Magic link + GitHub OAuth grátis; JWT + sessão DB |
| Clerk | UX premium, MFA, orgs prontas | $25/user-mo em escala; vendor lock-in |
| Supabase Auth | Bom | Adiciona dep desnecessária |
| Auth próprio | Total controle | Time-suck enorme |

### Storage

| Opção | Decisão |
|---|---|
| **Cloudflare R2** ✅ | S3-compat, sem egress fee — economia em export downloads |
| AWS S3 | Maturidade | Egress caro |
| Local FS | OK em dev |  Não escala |

### Hosting

| Opção | Decisão |
|---|---|
| **Vercel (web) + Fly.io (api/worker)** ✅ | Best-in-class para cada parte; preview deploys; regiões BR |
| Railway all-in-one | Simples | Menos flexível em workers |
| AWS / GCP | Power | Complexidade demais para solo MVP |

## Decisão

Stack final do MVP:

- **Backend:** FastAPI + Python 3.12, Pydantic v2, SQLAlchemy 2 async, Alembic.
- **Workers:** Arq (Fase 1.1).
- **DB:** PostgreSQL 16 (Neon).
- **Cache/queue:** Redis (Upstash).
- **LLM:** `litellm` como abstração.
- **Frontend:** Next.js 15 App Router + Tailwind + shadcn/ui + Recharts + Auth.js v5.
- **SDK:** `evalops-python` (httpx, dataclasses, jsonschema; sem pydantic).
- **Storage:** Cloudflare R2.
- **Hosting:** Vercel + Fly.io + Neon + Upstash.
- **Observability:** structlog, OpenTelemetry, Prometheus, Sentry.

## Consequências

**Positivas:**
- Coerência com portfólio Python.
- Eco LLMOps em Python é o mais maduro hoje (Q2 2026).
- Custos de infra previsíveis e baixos no MVP.
- DX excelente para autor solo.

**Negativas:**
- Workers Python async têm pegadinhas (event loop, libs sync vs async).
- Tipagem ponta-a-ponta com frontend exige geração de tipos OpenAPI (fricção menor).
- pydantic v2 + SQLAlchemy 2 ainda têm rough edges em integrações.

**Reversibilidade:** Média. Trocar backend exige reescrita; trocar provider de host é trivial.

## Quando reavaliar

- Se SDK TS virar prioridade (Fase 2): rever monorepo strategy.
- Se volume de traces exceder 5M: considerar ClickHouse para hot path.
- Se Auth.js v5 quebrar repetidamente: spike Clerk migration.
