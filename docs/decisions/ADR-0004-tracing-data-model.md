# ADR-0004 — Tracing Data Model: Trace + Span + Event hierárquico

- **Status:** Accepted
- **Data:** 2026-04-29

## Contexto

Aplicações com IA modernas raramente são "1 chamada de LLM". Um agente típico:
- Recebe input do usuário.
- Recupera docs do vector store (1+ retrieval).
- Chama LLM para reasoning.
- Executa tool calls.
- Chama LLM novamente para resposta.
- Aplica guardrails / fallback se necessário.

Como representar isso em DB de forma que:
- Queries sejam eficientes.
- Drill-down na UI seja simples.
- Custo agregado seja calculável sem JOINs caros.
- Compatibilidade com OpenTelemetry conceitual seja preservada.

## Opções consideradas

### A) Flat events (single table)

```
event:
  id, trace_id (string FK), event_type, timestamp, payload jsonb
```

**Prós:** simples; insert rápido; OTel-like.
**Contras:** reconstruir árvore exige todas as linhas + parent_id em payload; queries de "soma de tokens" exigem filtro por type; sem schema explícito por tipo.

### B) Trace + flat spans (sem aninhamento)

```
trace + span (sem parent_span_id)
```

**Prós:** simples; árvore "fake" só por tempo.
**Contras:** perde semântica de "esse tool call aconteceu dentro daquele agent_step".

### C) ✅ Trace + Span hierárquico + Event como filho de Span

```
trace
 └─ span (parent_span_id null = root)
     ├─ span (filho)
     │   └─ event (marcador pontual)
     └─ span (irmão)
```

**Prós:**
- Estrutura natural de agentes (trace é a sessão, spans são chamadas, events são marcadores).
- Custo agregado é `SUM(span.cost_usd) WHERE trace_id=X` — direto.
- Drill-down UI se torna rendering recursivo trivial.
- Compat conceitual com OTel (span tree).
- Tipagem por `span.type` permite filtros poderosos.

**Contras:**
- Insert envolve 3 tabelas (mas em batch dentro de uma transaction).
- Queries de "achar trace com tool call X" exigem JOIN.
- Limita profundidade (na prática, agente raramente passa de 5 níveis).

### D) Estilo Honeycomb (eventos arbitrários estilo wide-events)

**Prós:** flexível, agrega em alta cardinalidade. **Contras:** complexidade de schema; menos didático para portfólio.

## Decisão

**C) Trace + Span hierárquico + Event filho de Span.**

Schema implementado:

- `traces` (1 linha por sessão de IA do ponto de vista do produto).
- `spans` (1+ por trace; `parent_span_id` opcional → árvore).
- `events` (filho de span; marcador pontual sem duração).

Agregações no `traces` (denormalized):
- `total_tokens_in`, `total_tokens_out`.
- `total_cost_usd`.
- `duration_ms` = `max(span.ended_at) - min(span.started_at)`.

> **Por que denormalizar nos pais:** queries de overview ("custo do projeto no mês") são read-heavy e precisam ser baratas. Recomputar a partir de spans em cada request seria proibitivo. Tradeoff: insert paga 1 SUM extra, em transação.

Tipos de span suportados:
`llm_call`, `tool_call`, `retrieval`, `embedding`, `agent_step`, `chain`.

## Consequências

**Positivas:**
- Queries comuns são `SELECT * FROM traces WHERE project_id=? ORDER BY created_at DESC LIMIT N` — rápidas.
- Drill-down trace → span → event é hierarquia natural.
- Schema explícito por tipo de span (`llm_call` tem `model`, `tokens_*`, `cost_usd`; `tool_call` tem `input`/`output`/`error`).
- Compat conceitual com OTel facilita import futuro.

**Negativas:**
- 3 inserts por trace mínimo (trace + 1 span + 0 events). Em batch, ainda muito eficiente.
- Mudança de schema em `spans` (nova coluna) é dolorosa em alta escala. Mitigação: `metadata jsonb` para campos novos antes de migrar para coluna real.
- Exigir denormalização gera risco de drift entre `traces.total_*` e `SUM(spans)`. Mitigação: testes que recomputam e comparam em CI; reconciliação noturna.

**Reversibilidade:** Baixa. Migrar para flat events no futuro exigiria backfill caro.

## Decisões correlatas

- **IDs:** TEXT(26) ULID. Ordenáveis por tempo, gerados client-side, suficiente para volumes do MVP.
- **Particionamento:** não no MVP. Quando `traces` > 5M, particionar por mês (`PARTITION BY RANGE (created_at)`).
- **JSONB em messages_in/out:** sim, com truncation a 256KB por span (flag `_truncated=true` em metadata).
- **Indices:** `(project_id, created_at DESC)`, `(project_id, status, created_at DESC)`, `tags GIN`, `name gin_trgm` para search.

## Quando reavaliar

- Volume de spans > 5M no Postgres principal: considerar ClickHouse hot-path.
- Necessidade de import OTLP nativo: criar adapter, não mudar schema.
- Profundidade de span > 10 níveis em uso real: investigar (provavelmente bug do cliente).
