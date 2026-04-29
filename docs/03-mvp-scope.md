# 03 — MVP Scope

> O MVP é o **menor sistema que entrega valor demonstrável a Marina (AI Engineer)** e que serve de demo de portfólio com profundidade técnica suficiente. Foi cortado deliberadamente para caber em **6-10 semanas** de trabalho focado solo.

## 1. Princípios de corte

1. **Profundidade > largura.** Melhor 1 evaluator que funciona bem do que 8 quebrados.
2. **DX é feature.** SDK ruim invalida o resto. SDK Python no MVP é inegociável.
3. **Schema futuro-proof, código presente-mínimo.** Tabelas têm colunas para redaction, quotas, billing — mas a lógica é stub.
4. **Demo-first.** Cada decisão é validada por: "isso aparece no screenshot do portfólio?"

## 2. Dentro do MVP

### 2.1 Auth & Tenancy
- Magic link (Auth.js Email Provider) e GitHub OAuth.
- Modelo: `user → organization (1 default por user) → project (N) → api_key (N)`.
- Roles flat: `owner`, `member` na org.
- API keys: criação, revogação, rate limit básico (token bucket por key).

### 2.2 Tracing
- `POST /v1/traces` (batch, idempotente por `client_trace_id`).
- Tipos de span: `llm_call`, `tool_call`, `retrieval`, `embedding`, `agent_step`, `chain`.
- Custos: tabela de pricing por modelo (manual no MVP, atualizada em seed); cálculo em ingestion.
- SDK Python: `evalops.init`, `@trace`, `evalops.span()`, auto-instrumentação opcional para clients OpenAI/Anthropic/Gemini.

### 2.3 Avaliação
- Rubrica YAML versionada (`rubrics push` via CLI ou API).
- Evaluators no MVP:
  - `llm_judge` (one-shot LLM call com prompt template)
  - `regex_match`
  - `keyword_presence`
  - `length_bounds`
  - `json_schema_valid`
  - `exact_match`
  - `cosine_similarity` (embeddings)
- **Execução síncrona inline** (ou via endpoint manual) **no MVP**. Worker async em fila Redis é **Fase 1.1** (logo após MVP). Ver ADR-0003.
- Cada eval registra: `score (0..1)`, `passed (bool)`, `reasoning`, `cost_usd`, `latency_ms`, `evaluator_version`.

### 2.4 Versionamento de prompt & Experiments
- Tabela `prompt`, `prompt_version`. Diff textual simples (futuro: visual).
- Experiment: rodar dataset (lista de inputs) sobre N variants `(prompt_version, model)` → relatório agregado.
- Regression test suite: golden-set + critério de aceite por rubrica. CLI: `evalops experiment run <name>`.

### 2.5 Dashboard (Next.js)
- Telas: Login, Org overview, Project overview, Traces list, Trace detail, Rubrics list, Rubric detail, Experiments list, Experiment detail, API keys, Settings.
- Charts: custo/dia, tokens/dia, score médio por modelo, latência p50/p95.
- Sem alertas/email no MVP.

### 2.6 Feedback humano (mínimo)
- Endpoint `POST /v1/traces/{id}/feedback` com `{ thumbs, comment, user_ref }`.
- SDK helper `evalops.feedback(...)`.
- Lista de traces com feedback no dashboard.

### 2.7 Export de dataset
- `POST /v1/datasets/export` com filtros (date range, score range, tag, span_type) → job assíncrono → URL S3 (ou storage local em dev) com JSONL.
- Formato chat: `{"messages": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}], "meta": {...}}`.

### 2.8 Quotas (mockadas)
- Tabela `plan` (`free`, `pro`, `team`) com limites.
- Tabela `usage_counter` por org/mês.
- Enforcement bloqueia ingestion quando excede plano (no MVP, o limite default é alto e dificilmente atingido; serve para demonstrar arquitetura).
- **Sem cobrança real, sem Stripe.**

### 2.9 Self-observability
- Logs estruturados JSON.
- `/metrics` Prometheus.
- Sentry em produção.

## 3. Fora do MVP

| Item | Razão |
|---|---|
| Stripe / billing real | Esforço alto, não muda demo |
| Worker async (Arq) | Fase 1.1 — eval síncrono cobre demo inicial |
| Multi-region / HA | Single region é suficiente para portfolio |
| OTLP nativo | Custom payload é didático |
| RBAC granular | Roles flat resolvem 95% no MVP |
| Marketplace de rubricas | Distrai do core |
| Drift alerts (email/slack) | Bonito, mas não é demo killer |
| SDK TypeScript | Ficaria 50% pronto; melhor esperar |
| Mobile / PWA | N/A |
| ClickHouse para traces | Postgres aguenta o volume da demo (≤ 1M traces) |

## 4. Critérios de "Done"

### 4.1 Funcional
- [ ] Marina consegue cumprir UC-01 (instrumentação) em < 10 min do zero, com SDK publicado em PyPI (test PyPI no MVP é aceitável).
- [ ] UC-02 (auto-eval) funciona com rubrica `llm_judge` simples.
- [ ] UC-03 (regression em CI) tem CLI funcional retornando exit code correto.
- [ ] UC-06 (feedback) registra e exporta.
- [ ] UC-07 (demo de portfólio) tem 1 dos 3 projetos do autor instrumentado e gerando dados reais.

### 4.2 Não-funcional
- [ ] Cobertura de testes backend ≥ 70%.
- [ ] OpenAPI viva em `/docs`, atualizada via Pydantic.
- [ ] Deploy reproduzível com Docker Compose (local) e infraestrutura cloud (Vercel + Fly.io + Neon + Upstash).
- [ ] README do SDK com exemplo copy-paste para 3 frameworks (raw, LangGraph, CrewAI).

### 4.3 Demo de portfólio
- [ ] Vídeo de 90s mostrando: criar projeto → instrumentar agente → ver trace → criar rubrica → ver score → comparar 2 modelos.
- [ ] Print/screenshot único que conta a história em LinkedIn.
- [ ] Página `/changelog` no site com versões iniciais (vende disciplina de release).

## 5. Anti-MVP (NÃO fazer mesmo que tente)

- Implementar fila/worker antes do happy-path síncrono passar end-to-end.
- Implementar mais de 7 evaluators.
- Inventar UI de "rubric builder no-code" (rubrica é YAML, ponto).
- Suportar mais de 3 providers no SDK auto-instrument inicial (OpenAI, Anthropic, Gemini).
- Otimizar custo do worker antes de ter um worker.
- Internacionalização.

## 6. Linha do tempo macro (referência rápida)

Ver [`14-implementation-roadmap.md`](14-implementation-roadmap.md) para detalhe.

| Semana | Foco |
|---|---|
| 1 | Setup repo (mono ou dual), DB schema base, auth, projects, API keys |
| 2 | Endpoint ingestion + SDK Python v0.1.0 (sem auto-instrument) |
| 3 | Dashboard MVP: traces list + detail; SDK auto-instrument para OpenAI |
| 4 | Rubricas (YAML loader + 3 evaluators: regex, keyword, llm_judge); eval síncrono |
| 5 | Experiments + regression CLI; mais 4 evaluators |
| 6 | Feedback + export JSONL; quotas mockadas |
| 7 | Polish + demo do DocOps instrumentado + screenshots |
| 8 | Buffer / Fase 1.1 (worker async com Arq) |
