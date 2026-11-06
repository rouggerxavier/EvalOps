# evalops-python

Official Python SDK for EvalOps Studio.

## Install

```bash
pip install -e packages/sdk-python
```

## Quickstart (raw Python)

```python
import evalops

evalops.init(
    api_key="evk_prod_...",
    project="docops",
    environment="prod",
    service="docops-api",
    api_url="http://localhost:8000/v1",
)

@evalops.trace("docops.answer")
def answer(msg: str) -> str:
    with evalops.span("retrieve_context", type="retrieval") as sp:
        sp.set_io(input={"query": msg}, output={"hits": 3})
    return "ok"

answer("hello")
evalops.flush()
```

`flush(timeout=5.0)` waits up to `timeout` seconds for the background uploader
to send what is queued and returns `False` if something is still pending. It
does not guarantee that the backend has accepted every trace; retry-exhausted
transient failures are counted and written to local dead-letter files as
described below.

`shutdown(timeout=5.0)` stops the uploader within `timeout` seconds. What it
could not send by then, including a batch still in flight, goes to a
dead-letter file, and it returns `False`. It also runs at normal process exit
with the default timeout, and when `init()` is called again. A trace that
arrives after shutdown goes straight to dead-letter.

`environment` must be `dev`, `staging` or `prod`; `init` raises `ValueError` for
anything else.

The SDK never blocks the traced call: when the local queue (1024 traces) is
full, for example while the API is down, the new trace is dropped, a warning is
logged and `dropped_count` grows. When the API answers `2xx` but rejects single
traces in `errors[]`, each rejection is logged as a warning. Values that cannot
be sent as JSON never break the traced call: `NaN` and infinity become `null`,
and an object whose `repr()` raises becomes `<TypeName>`.

Each trace carries a `client_trace_id` generated once. Retries, requeues and
dead-letter replays resend the same id, and the API keeps one trace per id.

## Async

`@evalops.trace` works on `async def` functions too. Spans opened inside the
coroutine, including in tasks started with `asyncio.gather`, belong to its trace.
A cancelled coroutine is recorded with status `error`. A span opened after its
trace has closed is dropped. Generator functions, sync or async, raise
`TypeError` at decoration: trace the function that consumes them.

```python
@evalops.trace("support.turn")
async def answer(msg: str) -> str:
    with evalops.span("llm.generate", type="llm_call"):
        return await call_model(msg)
```

## Recording model calls

Rubrics and cost tracking read model calls recorded with `set_llm`:

```python
@evalops.trace("support.turn")
def answer(msg: str) -> str:
    with evalops.span("llm.generate") as sp:
        reply = call_model(msg)
        sp.set_llm(
            provider="openrouter",
            model=reply.model,
            messages_in=[{"role": "user", "content": msg}],
            messages_out=[{"role": "assistant", "content": reply.text}],
            tokens_in=reply.prompt_tokens,
            tokens_out=reply.completion_tokens,
            cost_usd=reply.cost,  # omit to price from the server table
        )
    return reply.text
```

## Describing a trace

Inside a trace, group turns and test runs with opaque ids. These values are stored
and shown as sent: never use a phone number or name.

```python
evalops.set_trace(conversation_id="c_8f2a", batch="bateria-2026-11-05", user_ref="u_91")
```

Rubrics read the earlier turns of a conversation in `trace.conversation.transcript`.

## LangGraph-style usage

```python
import evalops

evalops.init(api_key="evk_prod_...", project="aurora", environment="prod")

@evalops.trace("aurora.graph.run")
def run_graph(state: dict) -> dict:
    with evalops.span("planner", type="chain"):
        ...
    with evalops.span("tool_exec", type="tool_call"):
        ...
    return state
```

## CrewAI-style usage

```python
import evalops

evalops.init(api_key="evk_prod_...", project="imobiliaria", environment="prod")

@evalops.trace("imobiliaria.crew.kickoff")
def kickoff(task: str) -> str:
    with evalops.span("agent.research", type="chain"):
        ...
    with evalops.span("agent.reply", type="llm_call"):
        ...
    return "done"
```

## OpenAI auto-instrumentation

```python
ok = evalops.instrument_openai()
```

`instrument_openai()` is best-effort and safe to call even when OpenAI dependency is missing.
Calls with `stream=True` are not traced; record them with `set_llm`.

## Retry, dead-letter, and replay

The background uploader retries exceptions, HTTP `408`, HTTP `429`, and HTTP
`5xx` responses using the configured retry budget, then keeps the batch queued
and tries again with a growing delay of up to 60 seconds. Permanent `4xx`
responses other than `408` and `429`, such as a wrong key or an exhausted quota,
are not retried and do not create dead-letter files by default: the batch is
dropped and a warning with the status is logged.

When a transient failure still fails during a flush or shutdown, the SDK writes
one JSON dead-letter file per failed batch. The default directory is
`~/.evalops/dead/`; set `EVALOPS_DEAD_LETTER_DIR` to use another location.

Dead-letter files contain trace payloads. Those payloads can include prompts,
model outputs, user data, business data, or secrets supplied by application
code. The SDK does not persist API keys, `Authorization`, `X-EvalOps-Key`, or
arbitrary request headers, and the stored `api_url` is informational metadata
only.

Replay dead-letter files manually:

```python
import evalops

result = evalops.replay_dead_letter(
    dead_letter_dir="/tmp/evalops-dead",
    api_url="http://localhost:8000/v1",
    api_key="evk_prod_...",
)

print(result.files_seen, result.replayed, result.failed, result.removed)
```

If `api_url` or `api_key` are omitted, replay uses the current initialized SDK
configuration. Replay never uses the `api_url` stored in a dead-letter file as
the destination by default. A successful replay removes the dead-letter file;
a failed replay keeps it in place.

Replay resends old data. The API ignores a trace whose `client_trace_id` it
already stored, but answers `409` for a batch with a trace that was deleted
since. The SDK does not promise exactly-once delivery; review old payloads
before replaying them.

## Test

```bash
pytest packages/sdk-python/tests -q
```
