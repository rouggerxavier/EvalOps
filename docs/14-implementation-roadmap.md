# 14 — Implementation Roadmap

Plano de execução em **fases**, cada uma com entregáveis claros e critério de saída. Dimensionado para 1 desenvolvedor solo trabalhando ~20h/semana.

## 1. Visão geral

| Fase | Janela | Foco |
|---|---|---|
| **Fase 0** | Semana 0 | Setup, ADRs, scaffolding |
| **Fase 1 — MVP core** | Semanas 1-7 | Auth, ingestion, eval síncrono, dashboard, SDK |
| **Fase 1.1 — Hardening** | Semana 8 | Worker async, polish, demo de portfólio |
| **Fase 2** | Pós-MVP | Quality of life, snapshot de datasets, drift, webhooks |
| **Fase 3** | Futuro | Stripe billing, RBAC granular, OTLP, marketplace |

> Cada item abaixo é um entregável testável. Defeitos cosméticos não bloqueiam saída de fase.

## 2. Fase 0 — Setup (Semana 0)

**Objetivo:** começar a Fase 1 sem fricção.

- [ ] Decidir mono-repo vs dual-repo. **Recomendação:** mono-repo `EvalOps/` com `apps/api`, `apps/web`, `packages/sdk-python`.
- [ ] Criar repos secundários se necessário (p.ex. `evalops-python` se for distribuir SDK separado em PyPI).
- [ ] Bootstrapping API: FastAPI + Pydantic v2 + SQLAlchemy 2 + Alembic; pyproject + ruff + mypy.
- [ ] Bootstrapping Web: Next.js 15 + Tailwind + shadcn init + Auth.js v5.
- [ ] Bootstrapping SDK: pacote Python com pyproject; CI publish para Test PyPI.
- [ ] Docker Compose local: api, web, postgres, redis.
- [ ] CI básico (GitHub Actions): lint, type-check, test, build.
- [ ] Docs renderizados (Mintlify, Docusaurus ou só Markdown no repo). Recomendação: **Markdown no repo + GitHub Pages** no MVP.
- [ ] Aprovar ADRs 0001-0005 (escritos durante Fase 0).

**Saída de fase:** `docker compose up` sobe tudo; `pytest -q` passa em `apps/api` com testes de exemplo; deploy mínimo (Hello World) na cloud com domínio.

## 3. Fase 1 — MVP core (Semanas 1-7)

### 3.1 Semana 1 — Identity, Org, Project, API keys

- [ ] Migrations: `users`, `organizations`, `memberships`, `projects`, `api_keys`.
- [ ] Auth.js Email Provider + GitHub OAuth no Next.js.
- [ ] Endpoints: `/me`, `/organizations`, `/projects`, `/api-keys` (CRUD).
- [ ] Service: criação automática de Org default no signup.
- [ ] UI: login, onboarding, listagem de projetos, criar projeto, gerar API key (mostra uma vez).

**Critério:** Marina (de fora) consegue criar conta, projeto, key sem ajuda.

### 3.2 Semana 2 — Ingestion API + SDK Python v0.1.0

- [ ] Migrations: `traces`, `spans`, `events`.
- [ ] `POST /v1/traces` (batch, idempotente).
- [ ] Pricing table seed para 6 modelos.
- [ ] `IngestionService.calculate_costs`.
- [ ] SDK Python `evalops`: `init`, `@trace`, `span()` context manager. Sem auto-instrument.
- [ ] SDK publica em Test PyPI: `pip install -i https://test.pypi.org/simple/ evalops`.

**Critério:** rodar `python examples/quickstart.py` envia 10 traces e aparecem em `GET /v1/traces`.

### 3.3 Semana 3 — Dashboard MVP + Auto-instrument OpenAI

- [ ] UI: project overview (cards KPI estáticos calc-on-read), traces list (filtros mínimos), trace detail.
- [ ] Charts simples (custo/dia, tokens/dia).
- [ ] SDK: `instrument_openai()` patcha `openai.chat.completions` e `openai.embeddings`.

**Critério:** instrumentar projeto DocOps (pessoal) em ≤ 10 min e ver traces no dashboard real.

### 3.4 Semana 4 — Rubricas + 3 evaluators core + Eval síncrono

- [ ] Migrations: `rubrics`, `rubric_versions`, `evaluators`, `evaluation_runs`, `evaluation_scores`.
- [ ] YAML loader + Pydantic schema validator.
- [ ] Evaluators: `regex_match`, `keyword_presence`, `llm_judge` (via litellm, modelo default `gemini-2.5-flash` para baratear).
- [ ] `POST /v1/evaluations/run` síncrono.
- [ ] UI: lista de rubricas, editor YAML (Monaco) com validate, lista de runs no detalhe do trace.

**Critério:** rubric YAML enviada via `POST /v1/projects/{id}/rubrics` valida; rodar manual na UI mostra score.

### 3.5 Semana 5 — Mais 4 evaluators + Experiments + Regression CLI

- [ ] Evaluators restantes: `length_bounds`, `json_schema_valid`, `exact_match`, `cosine_similarity`.
- [ ] Migrations: `prompts`, `prompt_versions`, `datasets`, `dataset_items`, `experiments`, `experiment_runs`.
- [ ] Endpoints prompts/datasets/experiments.
- [ ] CLI `evalops` (Typer): `prompts push`, `rubrics push`, `experiment run --fail-on-regression`.
- [ ] Experiment execution (síncrono inline no MVP, fan-out limitado a 5 concurrent).

**Critério:** rodar regression suite via CLI, ver tabela markdown, exit code correto.

### 3.6 Semana 6 — Feedback + Export + Quotas mockadas

- [ ] Migrations: `human_feedback`, `export_jobs`, `plans`, `subscriptions`, `usage_counters`, `audit_logs`.
- [ ] `POST /v1/traces/{id}/feedback` + UI inline no detalhe do trace.
- [ ] Export JSONL chat (síncrono no MVP, timeout aceitável; async em Fase 1.1).
- [ ] Auto-eval em ingestion (lista `auto_eval_rubrics`).
- [ ] Counter de uso atualizado em ingestion + eval.

**Critério:** UC-06 (feedback → export) end-to-end. Counter `usage` reflete uso real.

### 3.7 Semana 7 — Polish + Demo de portfólio

- [ ] Empty states com snippet copy-paste em todas as telas vazias.
- [ ] Documentação OpenAPI rica + página `/docs` no site.
- [ ] README do SDK com 3 exemplos (raw, LangGraph, CrewAI).
- [ ] Instrumentar 1 dos projetos do autor (DocOps) e gerar 1 semana de dados reais.
- [ ] Vídeo de 90s do happy path.
- [ ] Deploy estável: Vercel (web), Fly.io (api), Neon (db), Upstash (redis).

**Critério MVP:** todos os items da seção 4 do `03-mvp-scope.md` checked.

## 4. Fase 1.1 — Hardening (Semana 8)

- [ ] **Worker async com Arq.** Migrar `evaluation.run` síncrono para enfileirado. Endpoint `POST /v1/evaluations/run` passa a retornar 202 + `run_id` (mantém compat com header `Prefer: respond-async=false` para forçar sync).
- [ ] **Export async.** Worker move-se de inline para fila Arq.
- [ ] **Cache de llm_judge.**
- [ ] **Rate limit decente** (token bucket Redis).
- [ ] **Sentry + structlog em produção.**
- [ ] **Bug bash** baseado em uso real de 1-2 semanas.

## 5. Fase 2 — Pós-MVP (4-8 semanas)

Ordem de prioridade sugerida:

1. **Snapshots de dataset** (imutáveis para experiments reproduzíveis).
2. **Compare 2 traces side-by-side** (UI).
3. **Drift alerts** (queda de score → email).
4. **SDK auto-instrument para Anthropic e Gemini.**
5. **OpenTelemetry import** (adapter externo OTLP → EvalOps).
6. **Webhooks.**
7. **PR comment bot** para regression em CI.
8. **Editor visual de prompt** com preview side-by-side.

## 6. Fase 3 — Futuro (não comprometido)

- Stripe billing real + portal.
- SDK TypeScript.
- Multi-region deployment.
- ClickHouse para hot-path de traces.
- RBAC granular + SSO SAML/OIDC.
- Marketplace de rubricas comunitário.
- Auto-tuning de prompt.
- Eval offline em batch sobre datasets externos.

## 7. Dependências críticas

| De | Depende de | Risco |
|---|---|---|
| Worker async | Eval síncrono ter API estável | Baixo |
| Auto-eval em ingestion | Worker async (preferível) | Médio — sem worker, ingestion bloqueia |
| Experiments | Datasets + Prompts + Rubrics | Alto se ordem invertida |
| Export | Datasets schema definido | Baixo |
| Demo de portfólio | DocOps instrumentado | Bloqueia entrega final |

## 8. Estimativa de risco de slip

| Risco | Mitigação |
|---|---|
| LLM judge custo explode em dev | Cache + Groq + cap por projeto |
| Schema do trace muda mid-MVP | Pinar shape do payload na semana 2; mudanças quebram clientes existentes do autor |
| Auth.js v5 com gotchas em prod | Spike de 1 dia na semana 1 |
| Editor Monaco YAML lerdo | Fallback para textarea + JSON Schema validation |
| Solo dev ficar sem motivação | Demo visível ao final de cada semana |

## 9. Definição de pronto (DoD) por feature

Toda feature considerada "done" quando:
- [ ] Endpoints relacionados têm testes (happy + 1 erro + 1 borda).
- [ ] Schema migration aplicada e revertida sem erro.
- [ ] OpenAPI atualizado e renderiza.
- [ ] UI tem empty state e error state.
- [ ] Mensagens de erro têm `code` estável e `docs_url`.
- [ ] Logs usam structlog (sem `print`).
- [ ] Sem TODOs `# critical:` no código.
