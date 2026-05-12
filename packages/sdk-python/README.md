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

## Test

```bash
pytest packages/sdk-python/tests -q
```
