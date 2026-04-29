# 07 — API Specification

API REST sob `https://api.evalops.studio/v1`. Documentação OpenAPI viva em `/docs` (FastAPI Swagger).

## 1. Convenções

- **Versionamento:** prefixo `/v1`. Mudanças breaking → `/v2`.
- **Auth:** dois modos:
  - **API key** via header `X-EvalOps-Key: evk_live_xxx` (apps clientes / SDK).
  - **Session** via cookie `__Secure-evalops.session` (dashboard). Internamente o BFF do Next.js converte cookie em JWT enviado em `Authorization: Bearer ...` para a API.
- **Content type:** `application/json; charset=utf-8`. Datas ISO-8601 UTC.
- **Paginação:** cursor-based. Query params `cursor`, `limit` (default 50, max 200). Resposta:
  ```json
  { "data": [...], "next_cursor": "eyJ0Ij..." | null }
  ```
- **Filtros:** query string com sintaxe simples (`?status=error&model=gpt-4o-mini&from=2026-04-01`). Filtros complexos via POST `/{resource}/search` body JSON.
- **Idempotência:** header `Idempotency-Key` aceito em todos os POSTs que criem recurso; servidor cacheia resposta por 24h.
- **Request ID:** servidor sempre retorna `X-Request-Id`; cliente pode enviar para correlação.
- **Rate limit headers:** `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`.

## 2. Modelo de erro

Toda resposta 4xx/5xx tem este shape:

```json
{
  "error": {
    "code": "trace_validation_failed",
    "message": "Field 'spans[0].started_at' must be ISO-8601",
    "request_id": "req_01HX...",
    "docs_url": "https://docs.evalops.studio/errors/trace_validation_failed",
    "details": [
      { "path": "spans[0].started_at", "issue": "invalid_format" }
    ]
  }
}
```

### Catálogo de códigos
| Código | HTTP | Quando |
|---|---|---|
| `unauthorized` | 401 | Sem credencial ou inválida |
| `forbidden` | 403 | Credencial válida sem permissão |
| `not_found` | 404 | Recurso inexistente OU sem permissão (por segurança) |
| `validation_failed` | 422 | Payload mal formado |
| `idempotency_conflict` | 409 | Mesma `Idempotency-Key` com body diferente |
| `rate_limit_exceeded` | 429 | Excedeu rate limit da key |
| `quota_exceeded` | 402 | Plano excedido |
| `internal_error` | 500 | Bug do servidor — request_id obrigatório |
| `dependency_unavailable` | 503 | DB/Redis fora |

## 3. Endpoints

### 3.1 Auth & contexto (uso do dashboard / BFF)

```
POST   /v1/auth/magic-link            { email }                       → 204
POST   /v1/auth/callback              { token } (validação magic)     → 200 { user, organizations }
POST   /v1/auth/oauth/github          { code }                        → 200
GET    /v1/me                                                          → 200 { user, organizations, current_org }
POST   /v1/me/switch-org              { organization_id }             → 200
DELETE /v1/me/sessions/{id}                                            → 204
```

### 3.2 Organizações & projetos

```
GET    /v1/organizations                                              → 200 { data: [Org] }
POST   /v1/organizations                {name, slug}                  → 201 { Org }
GET    /v1/organizations/{id}                                         → 200
PATCH  /v1/organizations/{id}           {name?, slug?}                → 200

GET    /v1/projects?organization_id=...                               → 200 { data, next_cursor }
POST   /v1/projects                     {name, slug, description?}    → 201 { Project }
GET    /v1/projects/{id}                                              → 200
PATCH  /v1/projects/{id}                                              → 200
POST   /v1/projects/{id}/archive                                      → 204
GET    /v1/projects/{id}/usage?period=2026-04                         → 200 { traces, evals, cost_usd }
```

### 3.3 API keys

```
GET    /v1/projects/{id}/api-keys                                     → 200 { data }   -- só metadata
POST   /v1/projects/{id}/api-keys       {name, environment, scopes?}  → 201 { ApiKey, key }   -- 'key' só uma vez
POST   /v1/projects/{id}/api-keys/{kid}/revoke                        → 204
```

Resposta de criação:
```json
{
  "id": "key_01HX...",
  "prefix": "evk_live_a1b2c3",
  "name": "production",
  "environment": "prod",
  "scopes": ["ingest","read"],
  "rate_limit_per_minute": 60,
  "created_at": "2026-04-29T12:00:00Z",
  "key": "evk_live_a1b2c3d4e5f6g7h8i9j0..."  // shown ONCE
}
```

### 3.4 Tracing (hot path)

#### POST `/v1/traces` — batch ingestion

```http
POST /v1/traces
X-EvalOps-Key: evk_live_xxx
Content-Type: application/json

{
  "traces": [
    {
      "client_trace_id": "ct_abc123",
      "name": "answer_user_question",
      "service": "aurora-support",
      "environment": "prod",
      "started_at": "2026-04-29T12:00:00.000Z",
      "ended_at":   "2026-04-29T12:00:01.450Z",
      "status": "ok",
      "tags": {"feature": "support"},
      "user_ref": "u_anon_a1b2",
      "spans": [
        {
          "client_span_id": "cs_1",
          "type": "llm_call",
          "name": "openai.chat.completions",
          "started_at": "2026-04-29T12:00:00.020Z",
          "ended_at":   "2026-04-29T12:00:01.420Z",
          "status": "ok",
          "provider": "openai",
          "model": "gpt-4o-mini",
          "messages_in": [...],
          "messages_out": [...],
          "tokens_in": 412, "tokens_out": 187
        }
      ]
    }
  ]
}
```

Resposta `202 Accepted`:
```json
{
  "ingested": 1,
  "results": [
    { "client_trace_id": "ct_abc123", "trace_id": "tr_01HX..." }
  ],
  "errors": []
}
```

Notas:
- Errors em items individuais não rejeitam o batch — vêm em `errors[]` com `index` e detalhe.
- `cost_usd` é calculado server-side via pricing table.
- Idempotência: re-POST com mesmo `client_trace_id` retorna o mesmo `trace_id`.

#### Listagem & detalhe
```
GET    /v1/traces?project_id=...&from=...&to=...&status=&model=&min_score=&max_score=&tag=&cursor=&limit=
                                                                       → 200 { data, next_cursor }
POST   /v1/traces/search    { filters JSON complexos }                → 200
GET    /v1/traces/{id}                                                → 200 { Trace, spans, events, evaluations, feedback }
DELETE /v1/traces/{id}                                                → 204   -- LGPD/GDPR
```

#### Feedback
```
POST   /v1/traces/{id}/feedback   { source, thumbs?, rating?, comment?, tags?, user_ref? }
                                                                       → 201
```

### 3.5 Rubrics

```
GET    /v1/projects/{id}/rubrics                                      → 200
POST   /v1/projects/{id}/rubrics       { yaml_source }                → 201 { Rubric, version: 1 }
GET    /v1/rubrics/{id}                                               → 200
GET    /v1/rubrics/{id}/versions                                      → 200
GET    /v1/rubrics/{id}/versions/{n}                                  → 200
POST   /v1/rubrics/{id}/versions       { yaml_source, changelog? }    → 201 { version: n+1 }
```

YAML é parseado e validado server-side (schema strict). Resposta inclui `parsed_spec`.

### 3.6 Evaluations

```
POST   /v1/evaluations/run        { trace_id, rubric_id, rubric_version? }
                                                                       → 201 { run } (sync no MVP) ou 202 { run_id, status: queued } (Fase 1.1)
GET    /v1/evaluations/{run_id}                                       → 200 { run + scores }
GET    /v1/traces/{id}/evaluations                                    → 200
```

### 3.7 Prompts

```
GET    /v1/projects/{id}/prompts                                      → 200
POST   /v1/projects/{id}/prompts        { slug, template, variables? } → 201
GET    /v1/prompts/{id}                                               → 200
GET    /v1/prompts/{id}/versions                                      → 200
POST   /v1/prompts/{id}/versions        { template, variables, changelog? }  → 201
```

### 3.8 Datasets

```
GET    /v1/projects/{id}/datasets                                     → 200
POST   /v1/projects/{id}/datasets       { slug, description?, source }  → 201
POST   /v1/datasets/{id}/items          { items: [{input, expected_output?, metadata?}] }  → 201
POST   /v1/datasets/{id}/build-from-traces  { filters }               → 202   -- async
GET    /v1/datasets/{id}/items?cursor=&limit=                         → 200
```

### 3.9 Experiments

```
GET    /v1/projects/{id}/experiments                                  → 200
POST   /v1/projects/{id}/experiments     { name, dataset_id, rubric_id, variants[], pass_criteria, baseline? }   → 201
POST   /v1/experiments/{id}/run          { triggered_by? }            → 202 { run_id }
GET    /v1/experiments/{id}/runs/{run_id}                             → 200
```

Resposta de run completo (resumida):
```json
{
  "run": {
    "id": "exr_01HX...",
    "status": "completed",
    "passed": true,
    "results": {
      "by_variant": {
        "v1_openai":  { "pass_rate": 0.96, "avg_score": 0.83, "total_cost_usd": 0.92 },
        "v1_gemini":  { "pass_rate": 0.94, "avg_score": 0.79, "total_cost_usd": 0.31 }
      },
      "regressions": []
    }
  }
}
```

### 3.10 Exports

```
POST   /v1/exports                       { project_id, filters, format }   → 202 { export_id }
GET    /v1/exports/{id}                                                    → 200 { status, url?, expires_at? }
```

### 3.11 Billing & quotas (mockado MVP)

```
GET    /v1/organizations/{id}/subscription                            → 200
GET    /v1/organizations/{id}/usage?period=YYYY-MM                    → 200
```

## 4. Webhooks (Futuro, não MVP)

```
events: trace.flagged, evaluation.completed, experiment.completed, export.ready
POST do EvalOps para a URL do cliente:
  body: { id, type, created_at, data }
  signature header: X-EvalOps-Signature: t=...,v1=hex(hmac_sha256(secret, t.body))
```

## 5. Rate limiting

- **API keys:** token bucket por key. Default 60 req/min, configurável.
- **Sessões dashboard:** 600 req/min por user.
- Resposta 429 com `Retry-After` em segundos.

## 6. CORS

- Origins permitidas: domínio do dashboard (`app.evalops.studio`) + `http://localhost:3000` em dev.
- API key endpoints são server-to-server: CORS irrelevante (não devem ser chamados de browser, mas não bloqueamos hard).

## 7. Versionamento de schema OpenAPI

- Cada release publica `openapi.json` versionado.
- Breaking changes → bump major (`/v2`).
- Adições não-breaking são livres em `/v1`.
- Geração de SDK (futuro): tipos TypeScript via `openapi-typescript`.

## 8. Exemplos de payload

Ver [`examples/trace-ingestion-payload.json`](examples/trace-ingestion-payload.json).
