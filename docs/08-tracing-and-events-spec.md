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
