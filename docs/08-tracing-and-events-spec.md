# 08 — Tracing & Events Spec

Define o **modelo conceitual**, **formato wire** e **comportamento do SDK** para tracing.

## 1. Modelo conceitual

```
Trace                        — uma execução de IA do ponto de vista do produto (ex.: "responder usuário")
 ├─ Span (root)             — primeira unidade de trabalho dentro do trace
 │   ├─ Span (filho)        — sub-passo (ex.: tool call)
 │   │   └─ Event           — marcador pontual (ex.: "fallback_triggered")
 │   └─ Span (filho)
 └─ Span (irmão do root)
```

**Trace** é a unidade de **negócio** (associada a "uma resposta ao usuário"). **Span** é a unidade de **execução** (uma chamada LLM, uma tool call). **Event** é um ponto temporal sem duração (anotação).

> Justificativa do modelo trace+span+event vs flat events: ADR-0004.

## 2. Tipos de span

| `type` | Quando usar | Campos típicos |
|---|---|---|
| `llm_call` | Chamada a um modelo de chat/completion/embeddings de chat | provider, model, messages_in, messages_out, tokens_in/out, cost_usd |
| `tool_call` | Execução de uma "função" pelo agente (function calling, ações) | name, input, output, error |
| `retrieval` | Busca em vector store / BM25 / SQL | input (query), output (docs/scores), metadata (top_k, filters) |
| `embedding` | Geração de embeddings | provider, model, input_count, tokens_in, cost_usd |
| `agent_step` | Iteração do agente (think/observe/act) | input (state), output (action), metadata (step_index) |
| `chain` | Wrapper para sequência arbitrária | input, output, metadata |

**Convenção de nomes:** o `name` do span deve ser estável e granular (ex.: `openai.chat.completions`, `pinecone.query.support_kb`, `tools.calendar.create_event`). Servirá para agregação no dashboard.

## 3. Formato wire (JSON)

### 3.1 Trace

```json
{
  "client_trace_id": "ct_<uuid-or-anything>",
  "name": "answer_user_question",
  "service": "aurora-support",
  "environment": "prod",
  "started_at": "2026-04-29T12:00:00.000Z",
  "ended_at":   "2026-04-29T12:00:01.450Z",
  "status": "ok",
  "tags": { "feature": "support", "channel": "web" },
  "user_ref": "u_anon_a1b2",
  "metadata": { "git_sha": "deadbeef" },
  "spans": [ /* ver §3.2 */ ]
}
```

Regras:
- `client_trace_id` é opcional mas **fortemente recomendado** para idempotência. Se ausente, servidor gera ULID novo.
- `status`: `ok`, `error` ou `partial` (alguns spans falharam mas o trace concluiu).
- `started_at`, `ended_at`: precisão de ms suficiente. `duration_ms` é derivado.
- `tags`: chave-valor flat de strings; usar `:` para namespace (`agent:imobiliaria_v3`).
- `user_ref`: hash/identificador anônimo do usuário final. **Nunca** PII direto.

### 3.2 Span

```json
{
  "client_span_id": "cs_root",
  "parent_client_span_id": null,
  "type": "llm_call",
  "name": "openai.chat.completions",
  "started_at": "2026-04-29T12:00:00.020Z",
  "ended_at":   "2026-04-29T12:00:01.420Z",
  "status": "ok",
  "provider": "openai",
  "model": "gpt-4o-mini",
  "prompt_version_ref": "support-answer-system@5",
  "messages_in": [
    {"role": "system", "content": "You are a helpful support agent..."},
    {"role": "user", "content": "Where is my order?"}
  ],
  "messages_out": [
    {"role": "assistant", "content": "Your order #123 ships tomorrow."}
  ],
  "tools": [
    {"name": "get_order_status", "description": "...", "parameters": {...}}
  ],
  "tokens_in": 412,
  "tokens_out": 187,
  "fallback_from_client_span_id": null,
  "metadata": { "temperature": 0.2 },
  "events": [ /* ver §3.3 */ ]
}
```

Regras:
- `parent_client_span_id` é referência **dentro do mesmo payload** (resolvido server-side para `parent_span_id`).
- `prompt_version_ref` aceita `slug@version` (preferido) ou ULID; servidor resolve.
- `messages_in/out` seguem o formato OpenAI chat (compat com tooling existente).
- Em `tool_call` use `input` / `output` / `error` ao invés de `messages_*`.
- `cost_usd` é calculado server-side se ausente; se cliente envia, server **valida** (em caso de divergência > 5%, persiste valor do cliente e flag `cost_mismatch=true`).

### 3.3 Event

```json
{
  "type": "fallback_triggered",
  "occurred_at": "2026-04-29T12:00:00.800Z",
  "payload": { "from": "gpt-4o-mini", "to": "gpt-4.1", "reason": "rate_limit_429" }
}
```

Tipos sugeridos (livres):
- `fallback_triggered`
- `guardrail_blocked`
- `cache_hit` / `cache_miss`
- `rate_limit_hit`
- `pii_redacted`
- `tool_choice_changed`
- `partial_response`

## 4. Cálculo de custo

Cost calculation server-side em `IngestionService`:

```python
def compute_cost(provider, model, tokens_in, tokens_out) -> Decimal:
    pricing = PRICING_TABLE[(provider, model)]  # {prompt_per_1k, completion_per_1k}
    return (tokens_in/1000 * pricing.prompt_per_1k +
            tokens_out/1000 * pricing.completion_per_1k)
```

Tabela de pricing é versionada (ver `app/infra/llm/pricing.py`); model desconhecido → cost=0 + flag `cost_unknown=true` no metadata do span.

## 5. SDK Python — `evalops`

### 5.1 API pública

```python
import evalops

evalops.init(
    api_key=os.environ["EVALOPS_API_KEY"],
    project="aurora-support",
    environment="prod",                # opcional, default = inferido por env var
    service="aurora-support",          # opcional
    tags={"git_sha": os.getenv("GIT_SHA", "dev")},
    sample_rate=1.0,                   # 0..1
    redact=evalops.redactors.email_phone(),  # opcional
    disabled=False,                    # quando True, vira no-op
)

# Decorator (caso simples)
@evalops.trace(name="answer_user_question")
def answer(user_msg: str) -> str:
    ...

# Context manager (para spans aninhados)
with evalops.span("retrieve_kb", type="retrieval") as sp:
    docs = vector_store.search(user_msg, k=5)
    sp.set_io(input={"query": user_msg, "k": 5}, output={"docs_ids": [d.id for d in docs]})

# Auto-instrument (opcional)
evalops.instrument_openai()      # patches openai.chat.completions, embeddings
evalops.instrument_anthropic()
evalops.instrument_gemini()

# Feedback (do end-user via backend)
evalops.feedback(trace_id="tr_...", thumbs="up", comment="...")
```

### 5.2 Comportamento interno

- **Background uploader:** thread daemon com fila bounded (default 1024). `flush_interval=2.0s`, `max_batch=64`.
- **Backoff:** retry 3x exponencial (0.5s, 1s, 2s) em `5xx` e timeout. `4xx` → drop com warning.
- **Falha silenciosa:** qualquer exceção do SDK NUNCA propaga (NFR-11). Logado via `logger.warning` se `evalops.set_log_level(WARNING)` setado.
- **Async support:** versão async dos decorators (`@evalops.trace_async`) e context manager (`async with evalops.span_async(...)`).
- **Sampling:** decidido no início do trace (root span). Se `random() > sample_rate`, todo o trace é descartado, sem custo.
- **Redaction client-side opcional:** `redact` é uma função `(msg: dict) -> dict`. Aplicada antes de enviar.
- **Modo `disabled`:** todos os helpers viram no-op. Útil em dev.

### 5.3 Pseudo-código do uploader

```python
class BackgroundUploader:
    def __init__(self, api_url, api_key, max_queue=1024, flush_interval=2.0, max_batch=64):
        self.queue = Queue(maxsize=max_queue)
        self.thread = Thread(target=self._loop, daemon=True)
        self.thread.start()

    def submit(self, trace: Trace) -> None:
        try:
            self.queue.put_nowait(trace)
        except Full:
            logger.warning("evalops queue full, dropping trace %s", trace.client_trace_id)

    def _loop(self) -> None:
        buf = []
        last_flush = time.time()
        while True:
            timeout = max(0.0, self.flush_interval - (time.time() - last_flush))
            try: buf.append(self.queue.get(timeout=timeout))
            except Empty: pass
            if len(buf) >= self.max_batch or time.time() - last_flush >= self.flush_interval:
                if buf: self._send(buf); buf.clear(); last_flush = time.time()
```

### 5.4 Compatibilidade

- Python 3.9+ (não 3.8: usaríamos `match`, `|` types, etc).
- Sem dep em pydantic v1; usa pydantic v2 internamente OU dataclasses simples (decisão MVP: **dataclasses + jsonschema** para reduzir conflitos com clientes que travam pydantic).
- HTTP via `httpx` (síncrono e async no mesmo cliente).

## 6. Idempotência & retry

| Cenário | Comportamento |
|---|---|
| Cliente reenvia mesmo `client_trace_id` | Server retorna mesmo `trace_id`; ignora payload novo |
| Servidor cai mid-batch | Cliente fará retry; idempotência protege |
| Rede flaky → 5xx | SDK retenta com backoff; cliente final não percebe |

**Window de idempotência:** 7 dias (ULID + UNIQUE index). Após isso, chave pode ser reutilizada sem efeito de dedup.

## 7. Métricas que o sistema deriva (read-side)

A partir de traces+spans, calculamos sob demanda:

- `traces_per_day_per_project`
- `tokens_per_day_per_model`
- `cost_per_day_per_feature` (via `tags.feature`)
- `latency_p50/p95/p99` por `name`
- `error_rate` por `model`
- `fallback_rate` (% de traces com pelo menos 1 span que tem `fallback_from_span_id`)

Implementação no MVP: queries SQL agregadas + cache curto (Redis 60s). Pre-aggregation (materialized views) é Futuro.

## 8. Open questions / decisões pendentes

- **[Decisão pendente]** Aceitar payload OpenTelemetry (OTLP) nativo? Recomendação: **não** no MVP; converter via adapter externo se necessário.
- **[Decisão pendente]** Comprimir batch (gzip/brotli) no SDK? Recomendação: **gzip opt-in** quando batch > 50KB.
- **[Decisão pendente]** Limite de tamanho de mensagem (`messages_in/out`)? Recomendação: **256KB por span**, truncar com `..._truncated=true`.

## 9. Recommended RAG trace convention

> **Status:** convenção **opcional e recomendada**, não contrato rígido. EvalOps permanece genérico — qualquer aplicação pode emitir traces sem seguir esta seção. A convenção existe só para que UI, evaluators e datasets futuros possam **destacar automaticamente** dados de pipelines RAG quando estiverem presentes. Nomes, tipos de span e chaves abaixo são *defaults sugeridos*, não validados pelo schema.
>
> Aplicações podem mandar dados arbitrários via `Trace.metadata`, `Span.input`, `Span.output`, `Span.metadata` e `Event.payload` — todos já são JSON livre no schema atual (ver §3). Esta seção apenas propõe **quais chaves usar** para maximizar interoperabilidade.

### 9.1 Princípios

1. **Opcional.** Trace que não segue esta convenção continua sendo aceito sem perda.
2. **Aditivo.** Se faltar um span ou campo recomendado, EvalOps degrada graciosamente — não rejeita.
3. **Privacidade-first.** Conteúdo bruto de usuário, documento ou prompt renderizado é evitado por padrão (ver §9.5).
4. **Sem hardcode de aplicação.** Exemplos abaixo usam `example-rag-service`; nomes reais de aplicação não viram contrato.
5. **Fixtures vs contrato.** Payloads concretos de aplicações reais devem morar em `packages/sdk-python/tests/fixtures/` e `docs/examples/`, não como regra normativa.

### 9.2 Trace recomendado

| Campo | Valor sugerido | Notas |
|---|---|---|
| `name` | `"<service>.<flow>.rag_request"` | livre; estável e granular (§2) |
| `service` | nome do serviço emissor | |
| `environment` | `dev` / `staging` / `prod` | enum do schema |
| `status` | `ok` / `error` / `partial` | `partial` sugerido para "no-answer" / fallback parcial |
| `tags.pipeline` | `"rag"` (opcional) | facilita filtro/rollup futuro |
| `metadata.pipeline_version` | string (ex.: `"v3"`) | versão lógica do pipeline RAG |
| `metadata.model` | string (ex.: `"gpt-4o-mini"`) | rollup leve do modelo principal de generation |
| `metadata.total_latency_ms` | int | redundante com `duration_ms` derivado, mas útil quando emissor mede separadamente |
| `metadata.strict_grounding` | bool | indica se o pipeline rejeita resposta sem evidência |
| `metadata.retrieved_count` | int | rollup do `rag.retrieve` |
| `metadata.has_answer` | bool | se o pipeline produziu resposta |
| `metadata.citation_count` | int | rollup de citações |
| `metadata.grounding_score` ou `metadata.support_rate` | float `[0,1]` | rollup, se calculado pelo emissor |

Nenhum desses campos é obrigatório. Ausência ≠ erro.

### 9.3 Spans recomendados

Convenção: cinco etapas comuns em pipelines RAG. Cada uma é opcional; pipelines podem fundir/omitir. `type` segue a taxonomia da §2 (livre, mas as escolhas abaixo permitem reuso de UI/cores existentes).

#### 9.3.1 `rag.retrieve`

| Aspecto | Valor recomendado |
|---|---|
| `type` | `retrieval` |
| `name` | `"rag.retrieve"` (ou granular: `"pinecone.query.support_kb"`) |
| `input` | `{ "query": "<truncated>", "top_k": int, "filters": {...} }` |
| `output` | `{ "retrieved_count": int, "top_score": float, "chunks": [ { "id": "<hash>", "score": float, "source": "<doc_ref>", "snippet": "<truncated>" } ] }` |
| `metadata` | `{ "index": "...", "embedding_model": "...", "embedding_provider": "..." }` |
| Top-level span | `provider` e `model` se aplicável ao embedder |

#### 9.3.2 `rag.context.build`

| Aspecto | Valor recomendado |
|---|---|
| `type` | `chain` |
| `name` | `"rag.context.build"` |
| `input` | `{ "chunk_ids": ["..."], "strategy": "concat/rerank/..." }` |
| `output` | `{ "context_tokens": int, "context_chunk_count": int }` |
| `metadata` | `{ "reranker_model": "...", "max_context_tokens": int }` |

#### 9.3.3 `llm.generate`

| Aspecto | Valor recomendado |
|---|---|
| `type` | `llm_call` |
| `name` | `"llm.generate"` (ou granular: `"openai.chat.completions"`) |
| Top-level | `provider`, `model`, `prompt_version_ref`, `tokens_in`, `tokens_out`, `cost_usd` |
| `messages_in` / `messages_out` | formato OpenAI; **truncar** ou omitir se sensível |
| `output` | `{ "answer": "<truncated>", "answer_preview": "<≤500 chars>", "finish_reason": "stop" }` |
| `metadata` | `{ "temperature": ..., "max_tokens": ..., "seed": ... }` |

#### 9.3.4 `rag.grounding.validate`

| Aspecto | Valor recomendado |
|---|---|
| `type` | `tool_call` |
| `name` | `"rag.grounding.validate"` |
| `input` | `{ "answer_ref": "<span_id ou hash>", "chunk_ids": ["..."] }` |
| `output` | `{ "grounded": bool, "score": float, "support_rate": float, "unsupported_claims_count": int }` |
| `metadata` | `{ "validator": "llm/rule-based/..." }` |
| Top-level | `provider`/`model`/`tokens_*`/`cost_usd` se validator for LLM |

#### 9.3.5 `response.finalize`

| Aspecto | Valor recomendado |
|---|---|
| `type` | `chain` |
| `name` | `"response.finalize"` |
| `output` | `{ "answer_preview": "<truncated>", "has_answer": bool, "citation_count": int, "citations": [ { "chunk_id": "<hash>", "span_text_preview": "<truncated>" } ] }` |
| `metadata` | `{ "post_processing": "..." }` |

### 9.4 Eventos sugeridos (RAG-flavored)

Reusam o canal `Event` da §3.3 — todos `payload` JSON livre.

- `retrieval.empty` — `{ "query_hash": "..." }`
- `retrieval.low_recall` — `{ "top_score": 0.31, "threshold": 0.5 }`
- `grounding.failed` — `{ "score": 0.42, "min_required": 0.7 }`
- `answer.refused` — `{ "reason": "no_grounded_evidence" }`
- `fallback_triggered` — já existe na §3.3
- `pii_redacted` — já existe

### 9.5 Política de privacidade

A regra geral: **enviar o mínimo necessário para avaliar, não para reconstruir o pedido do usuário.**

| Categoria | Política | Exemplos |
|---|---|---|
| **Seguro enviar bruto** | livre | contagens, status, latências, flags booleanas, scores numéricos, `top_k`, `temperature`, `finish_reason` |
| **Preferir hash/id opaco** | hash determinístico ou ULID interno | `user_id`, `doc_id`, `chunk_id`, `session_id`, `tenant_id` |
| **Truncar** | limite curto (sugestão: 500 chars) + sufixo `_truncated=true` no metadata do span | `query`, `answer_preview`, `chunk_preview`, `unsupported_claims[].text` |
| **Não enviar por padrão** | omitir; ativar só em dev/dogfood com decisão explícita | documento completo, chunk completo, prompt renderizado completo, paths de arquivo locais, secrets/tokens, stack traces brutos |
| **Redaction opt-in** | usar `tags.pii=true` ou header `X-EvalOps-Redact` | qualquer trace que cruzar input livre de usuário sem sanitização prévia |

Dogfood/dev pode liberar mais detalhe **se** o emissor decidir explicitamente (flag de ambiente, não default). Em prod, default = mínimo.

### 9.6 Tokens & custo

- Enviar `tokens_in`, `tokens_out`, `cost_usd` em `llm.generate` (e em `rag.grounding.validate` se for LLM) **somente quando conhecidos**.
- **Não inventar** valores. Se desconhecidos, omitir o campo (nullable no schema) ou deixar zero conforme o contrato atual do trace.
- Server-side `compute_cost` (§4) preenche `cost_usd` quando ausente e `(provider, model)` existir na pricing table; caso contrário, `cost=0` + `cost_unknown=true` no metadata.
- Trace rollups `total_tokens_in/out/total_cost_usd` são derivados da soma dos spans. Se nenhum span enviar tokens, totais ficarão zero — comportamento esperado.
- **Tokens/cost aparecem quando o provider expuser `usage` confiável.** Quando o pipeline emissor ainda não captura `usage` (provider sem retorno estável, streaming sem reconciliação, validador rule-based), os campos podem ficar ausentes ou zero — isso deve ser registrado como limitação conhecida do emissor, **não bloqueia** a adoção desta convenção nem qualquer rollout incremental (ex.: D1). Reconciliação de tokens/cost pode evoluir em fases posteriores sem invalidar traces já emitidos.

### 9.7 Exemplo JSON pequeno

Genérico, sem dados reais, service de exemplo `example-rag-service`:

```json
{
  "client_trace_id": "ct_example_001",
  "name": "example-rag-service.chat.rag_request",
  "service": "example-rag-service",
  "environment": "prod",
  "started_at": "2026-05-19T10:00:00.000Z",
  "ended_at":   "2026-05-19T10:00:01.800Z",
  "status": "ok",
  "tags": { "pipeline": "rag" },
  "user_ref": "u_hash_abc123",
  "metadata": {
    "pipeline_version": "v3",
    "model": "gpt-4o-mini",
    "total_latency_ms": 1800,
    "strict_grounding": true,
    "retrieved_count": 4,
    "has_answer": true,
    "citation_count": 2,
    "grounding_score": 0.86
  },
  "spans": [
    {
      "client_span_id": "cs_retrieve",
      "parent_client_span_id": null,
      "type": "retrieval",
      "name": "rag.retrieve",
      "started_at": "2026-05-19T10:00:00.020Z",
      "ended_at":   "2026-05-19T10:00:00.180Z",
      "status": "ok",
      "input":  { "query": "how do refunds work?", "top_k": 4 },
      "output": {
        "retrieved_count": 4,
        "top_score": 0.82,
        "chunks": [
          { "id": "ch_h1", "score": 0.82, "source": "doc_h7", "snippet": "Refunds are issued within 5..." },
          { "id": "ch_h2", "score": 0.74, "source": "doc_h7", "snippet": "To request a refund, open..." }
        ]
      },
      "metadata": { "index": "kb_main", "embedding_model": "text-embedding-3-small" }
    },
    {
      "client_span_id": "cs_generate",
      "parent_client_span_id": null,
      "type": "llm_call",
      "name": "llm.generate",
      "started_at": "2026-05-19T10:00:00.220Z",
      "ended_at":   "2026-05-19T10:00:01.620Z",
      "status": "ok",
      "provider": "openai",
      "model": "gpt-4o-mini",
      "prompt_version_ref": "rag-answer-system@7",
      "tokens_in": 612,
      "tokens_out": 148,
      "output": {
        "answer_preview": "Refunds are issued within 5 business days...",
        "finish_reason": "stop"
      },
      "metadata": { "temperature": 0.2 }
    },
    {
      "client_span_id": "cs_ground",
      "parent_client_span_id": null,
      "type": "tool_call",
      "name": "rag.grounding.validate",
      "started_at": "2026-05-19T10:00:01.640Z",
      "ended_at":   "2026-05-19T10:00:01.760Z",
      "status": "ok",
      "output": {
        "grounded": true,
        "score": 0.86,
        "support_rate": 0.92,
        "unsupported_claims_count": 0
      }
    },
    {
      "client_span_id": "cs_final",
      "parent_client_span_id": null,
      "type": "chain",
      "name": "response.finalize",
      "started_at": "2026-05-19T10:00:01.770Z",
      "ended_at":   "2026-05-19T10:00:01.795Z",
      "status": "ok",
      "output": {
        "answer_preview": "Refunds are issued within 5 business days...",
        "has_answer": true,
        "citation_count": 2,
        "citations": [
          { "chunk_id": "ch_h1", "span_text_preview": "issued within 5 business days" },
          { "chunk_id": "ch_h2", "span_text_preview": "open the order page and click Refund" }
        ]
      }
    }
  ]
}
```

### 9.8 Implicações futuras (não comprometem nada hoje)

Esta convenção **não** implica que evaluators ou flows abaixo já existem — só sugere onde dados podem ser consumidos quando/se forem implementados:

- `output.answer` ou `output.answer_preview` do último span de generation/finalize pode servir como **resposta candidata** para evaluators determinísticos ou `llm_judge`.
- `output.chunks[]` (`rag.retrieve`) e `output.citations[]` (`response.finalize`) podem alimentar evaluators de **groundedness / faithfulness / citation-coverage / context-precision** quando existirem.
- `metadata.pipeline_version` / `metadata.model` no trace podem virar dimensões de filtro/segmentação no dashboard.
- `build-from-traces` (datasets) pode aprender a popular `input`/`expected_output` a partir desses campos quando `messages_in/out` estiverem ausentes.

Nenhum desses consumos existe hoje; a convenção apenas reserva o **shape** para que a implementação futura encontre dados estáveis.
