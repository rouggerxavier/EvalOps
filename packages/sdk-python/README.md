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

`flush()` drains the local SDK queue. It does not guarantee that the backend has
accepted every trace; retry-exhausted transient failures are counted and written
to local dead-letter files as described below.

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

## Retry, dead-letter, and replay

The background uploader retries exceptions, HTTP `408`, HTTP `429`, and HTTP
`5xx` responses using the configured retry budget. Permanent `4xx` responses
other than `408` and `429` are not retried and do not create dead-letter files
by default.

When a transient failure still fails after retries are exhausted, the SDK writes
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

Replay can resend old data and can duplicate traces or ingest if the backend
accepts the same payload more than once. The SDK does not promise exactly-once
delivery; review old payloads before replaying them.

## Test

```bash
pytest packages/sdk-python/tests -q
```
