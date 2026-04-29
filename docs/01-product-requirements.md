# 01 — Product Requirements

Este documento define os requisitos **funcionais** e **não-funcionais** do EvalOps Studio. Cada requisito tem ID estável (`FR-*` / `NFR-*`) que é referenciado em testes, ADRs e roadmap.

## 1. Requisitos funcionais

### 1.1 Onboarding & Projetos

| ID | Requisito | Prioridade |
|---|---|---|
| FR-01 | Usuário pode criar conta com email + magic link OU GitHub OAuth | **MVP** |
| FR-02 | Usuário pertence a uma `organization`; organization pode ter múltiplos projetos | **MVP** |
| FR-03 | Usuário pode criar/renomear/arquivar projetos | **MVP** |
| FR-04 | Cada projeto tem `name`, `slug`, `description`, `default_environment` (`dev`/`staging`/`prod`) | **MVP** |
| FR-05 | Convite de membros com roles (`owner`, `admin`, `member`, `viewer`) | Recomendado |
| FR-06 | RBAC granular por projeto | Futuro |

### 1.2 API Keys

| ID | Requisito | Prioridade |
|---|---|---|
| FR-10 | Usuário pode gerar API keys por projeto, com nome e environment | **MVP** |
| FR-11 | API key é mostrada **uma única vez** após criação; persistida apenas como hash (argon2) | **MVP** |
| FR-12 | Prefixo da key (`evk_live_a1b2c3...`) é visível no dashboard para identificação | **MVP** |
| FR-13 | Key pode ser revogada a qualquer momento; revogação tem efeito em < 60s | **MVP** |
| FR-14 | Cada key registra `last_used_at` e contador de uso para detecção de inatividade | Recomendado |
| FR-15 | Rate limiting por key (configurável por plano; default 60 req/min) | **MVP** |
| FR-16 | Scoped keys (read-only, ingest-only, full) | Futuro |

### 1.3 Tracing

| ID | Requisito | Prioridade |
|---|---|---|
| FR-20 | API HTTP `POST /v1/traces` aceita batch de traces+spans+events | **MVP** |
| FR-21 | SDK Python expõe `@trace` decorator que captura inputs/outputs automaticamente | **MVP** |
| FR-22 | SDK Python expõe context manager `with evalops.span("name")` para spans aninhados | **MVP** |
| FR-23 | SDK envia em background com batching e retry exponencial; nunca bloqueia request do usuário | **MVP** |
| FR-24 | Cada trace registra: provider, modelo, prompt, resposta, mensagens completas, tools, tokens (in/out), custo USD, latência, status, erro, fallback flag, metadados livres | **MVP** |
| FR-25 | Suporte a tipos de span: `llm_call`, `tool_call`, `retrieval`, `embedding`, `agent_step`, `chain` | **MVP** |
| FR-26 | Sampling configurável por projeto (e.g., 10% prod) | Recomendado |
| FR-27 | Redação automática de campos marcados como `sensitive` (PII via Presidio) | Recomendado (off por default) |
| FR-28 | Importação de OpenTelemetry traces | Futuro |

### 1.4 Avaliação

| ID | Requisito | Prioridade |
|---|---|---|
| FR-30 | Usuário pode definir rubricas em YAML (declarativas) | **MVP** |
| FR-31 | Tipos de evaluator suportados no MVP: `llm_judge`, `regex_match`, `keyword_presence`, `length_bounds`, `json_schema_valid`, `exact_match`, `cosine_similarity` | **MVP** |
| FR-32 | Rubrica retorna `score` (0..1) + `passed` (bool) + `reasoning` (str opcional) | **MVP** |
| FR-33 | Rubricas são versionadas (semver); rubrica v2 não invalida runs antigos | **MVP** |
| FR-34 | Avaliação roda assíncrona em fila Redis (Arq) | Recomendado (Fase 1.1) |
| FR-34a | Avaliação no MVP pode rodar **síncrona** inline ou em endpoint manual `POST /evaluations/run` | **MVP** |
| FR-35 | Avaliação programada: trigger por novo trace OU por agendamento OU manual | **MVP** (manual + por trace) |
| FR-36 | Avaliação composta: rubrica pode chamar múltiplos evaluators e agregar (mean/min/weighted) | **MVP** |
| FR-37 | Custo de cada avaliação (LLM judge) é registrado e somado ao trace | **MVP** |
| FR-38 | Meta-eval: dashboards mostram concordância entre rubrica automática e feedback humano | Futuro |

### 1.5 Versionamento de prompt/modelo & Experiments

| ID | Requisito | Prioridade |
|---|---|---|
| FR-40 | Prompts são entidade versionada (`prompt_id`, `version`, `template`, `variables`, `metadata`) | **MVP** |
| FR-41 | Diff visual entre versões de prompt | Recomendado |
| FR-42 | Experiment: rodar dataset X em (prompt_v1, modelo_A) vs (prompt_v2, modelo_B) e comparar métricas agregadas | **MVP** |
| FR-43 | Regression test suite: golden-set de N pares (input, expected) com critério de aceite (e.g., 95% dos casos passam rubrica X) | **MVP** |
| FR-44 | API para CI: `POST /experiments/run` retorna `passed: bool` + relatório | Recomendado |
| FR-45 | Webhook em fim de experiment | Futuro |

### 1.6 Dashboard & Analytics

| ID | Requisito | Prioridade |
|---|---|---|
| FR-50 | Tela de overview do projeto: # traces, # erros, custo USD/dia, latência p50/p95, score médio | **MVP** |
| FR-51 | Lista paginada de traces com filtros (status, modelo, score range, date range, tag) | **MVP** |
| FR-52 | Detalhe de trace: árvore de spans, mensagens, tools, eval scores, cost breakdown | **MVP** |
| FR-53 | Charts: custo por dia, tokens por dia, score médio por modelo, latência por endpoint | **MVP** |
| FR-54 | Comparação side-by-side de dois traces (mesmo input, modelos diferentes) | Recomendado |
| FR-55 | Alertas em queda de score (drift detection) | Futuro |

### 1.7 Human Feedback & Datasets

| ID | Requisito | Prioridade |
|---|---|---|
| FR-60 | Trace pode receber feedback `thumbs` (👍/👎) + comment via SDK e via API | **MVP** |
| FR-61 | Dashboard tem fila de revisão humana (traces com score < threshold OU sem rubrica) | Recomendado |
| FR-62 | Reviewer humano anota: `quality_score` (1-5), `tags`, `corrected_response` opcional | Recomendado |
| FR-63 | Export de dataset em JSONL (formato chat: `messages: [...]`) com filtros | **MVP** |
| FR-64 | Export é compatível com formato HuggingFace `datasets` | **MVP** |
| FR-65 | Export de DPO/RLHF pairs (preferred vs rejected) | Futuro |

### 1.8 Billing & Quotas

| ID | Requisito | Prioridade |
|---|---|---|
| FR-70 | Sistema rastreia uso (traces ingeridos, evals rodados, custo de LLM judge) por organization e mês | **MVP** |
| FR-71 | Schema de `plans` e `subscriptions` está pronto, mas sem cobrança real | **MVP** (mockado) |
| FR-72 | Integração com Stripe (checkout, webhooks, portal) | Futuro |
| FR-73 | Quota enforcement: bloqueia ingestion se org excedeu plano | Recomendado |

## 2. Requisitos não-funcionais

### 2.1 Performance

| ID | Requisito | Alvo |
|---|---|---|
| NFR-01 | Latência de `POST /v1/traces` (p95) | < 150 ms (apenas enfileiramento) |
| NFR-02 | Throughput de ingestion por instância da API | ≥ 200 traces/s |
| NFR-03 | Lag fila → eval rodado (p95) | < 30 s |
| NFR-04 | Tempo de carregamento do dashboard (cold) | < 2 s (LCP) |
| NFR-05 | Query de listagem de traces com filtros (10k traces) | < 500 ms |

### 2.2 Disponibilidade & Resiliência

| ID | Requisito |
|---|---|
| NFR-10 | Ingestion API tem 99.5% de disponibilidade no MVP (objetivo, não SLA contratual) |
| NFR-11 | SDK NUNCA bloqueia ou quebra a aplicação cliente em caso de erro do EvalOps; falhas são silenciosas + log opcional |
| NFR-12 | Idempotência: cliente pode retry com mesmo `client_trace_id` sem duplicar |
| NFR-13 | Worker de eval é at-least-once com deduplicação por `(trace_id, rubric_version)` |

### 2.3 Segurança

| ID | Requisito |
|---|---|
| NFR-20 | Todas as conexões via HTTPS/TLS 1.3 |
| NFR-21 | API keys armazenadas como hash argon2id (memory cost ≥ 19 MiB, 2 lanes) |
| NFR-22 | Secrets (DB, providers) via env vars; nunca em código |
| NFR-23 | RLS-ready: queries sempre filtram por `organization_id` (enforced no repository layer) |
| NFR-24 | Rate limit por API key e por IP |
| NFR-25 | Audit log de operações sensíveis (criação/revogação de key, mudança de plano) |

### 2.4 Privacidade & Compliance

| ID | Requisito |
|---|---|
| NFR-30 | Schema permite redaction; campo `redacted` em prompts/respostas |
| NFR-31 | Dados de trace podem ser deletados sob demanda (LGPD/GDPR right to erasure) — endpoint `DELETE /v1/traces/{id}` |
| NFR-32 | Retenção configurável por projeto (default 90 dias no MVP, 30 dias no plano free) |
| NFR-33 | Logs do sistema NÃO podem conter conteúdo de prompts/respostas (apenas IDs e metadata) |

### 2.5 Observabilidade do próprio EvalOps

| ID | Requisito |
|---|---|
| NFR-40 | Logs estruturados JSON (structlog) |
| NFR-41 | Métricas Prometheus expostas em `/metrics` (latência, tx ingestion, fila, erros) |
| NFR-42 | Traces OpenTelemetry exportáveis para Honeycomb/Grafana Tempo |
| NFR-43 | Sentry para exceções não tratadas |

### 2.6 DX (Developer Experience)

| ID | Requisito |
|---|---|
| NFR-50 | SDK Python instala via pip; instrumentação básica em ≤ 3 linhas |
| NFR-51 | API tem documentação OpenAPI viva em `/docs` |
| NFR-52 | Erros da API retornam `error.code` estável + `error.message` humano + `error.docs_url` |
| NFR-53 | SDK roda em modo `disabled=True` para dev local sem credenciais |

## 3. Critérios de "MVP done"

O MVP está pronto quando:

- [ ] Usuário cria conta, cria projeto, gera key.
- [ ] Instrumenta DocOps Agent com SDK em < 10 minutos.
- [ ] Vê traces no dashboard em tempo real.
- [ ] Cria rubrica YAML, dispara eval, vê score no trace.
- [ ] Roda regression test suite manualmente e vê pass/fail por caso.
- [ ] Exporta dataset JSONL filtrando por score.
- [ ] Todos os endpoints públicos têm OpenAPI; cobertura de testes ≥ 70% no backend.

## 4. Fora de escopo (explícito)

Os itens abaixo são **deliberadamente** deixados de fora do MVP, mesmo sendo úteis. Listados aqui para evitar scope creep:

- Stripe billing real
- RBAC granular (apenas roles flat no MVP)
- Multi-region
- Suporte a OTLP nativo
- Eval offline em batch sobre datasets externos (apenas sobre traces ingeridos)
- Mobile app
- Marketplace de rubricas
- Auto-tuning de prompt
- Drift alerts via email/Slack
