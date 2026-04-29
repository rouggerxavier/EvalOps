# evalops-python

SDK Python oficial do EvalOps Studio (MVP inicial).

## Quickstart

```python
import evalops

evalops.init(
    api_key="evk_prod_...",
    project="docops",
    environment="prod",
    service="docops-api",
    api_url="http://localhost:8000/v1",
)

@evalops.trace("docops.summarize")
def summarize(text: str) -> str:
    with evalops.span("retrieve_context", type="retrieval") as sp:
        sp.set_io(input={"q": text}, output={"hits": 3})
    return "summary"
```

Auto-instrument OpenAI (best effort):

```python
evalops.instrument_openai()
```
