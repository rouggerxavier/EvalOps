# EvalOps — Async Worker + Trace Replay Spec

Data: 2026-05-21
Branch base: `claude/repository-access-X2Zcv`
HEAD base: `df18a5f`
Escopo: especificação, gap analysis e plano de execução por fase. Nenhum código produtivo, migration, schema, infra, ou push foi realizado neste documento.

Origem: Bug #1 do code review `docs/audits/tentativa_refactor-code-review-2026-05-21.md`

---

## 1. Contexto

### Estado atual da rota `POST /v1/traces/{id}/rerun`

A rota existe em `apps/api/app/api/routes_trace_actions.py:291-330` e responde
`{ "new_trace_id": "...", "status": "queued" }`, mas **não enfileira nenhum job**.
Cria um `Trace` placeholder com `status="partial"`, todos os contadores zerados, e
`metadata.replay_of = original_trace_id`. Nenhum worker reexecuta o prompt.

Impacto direto:
- Trace fantasma fica eternamente em `partial` com zero dados.
- Cada clique no botão "Reexecutar" cria mais um stub.
- p95, taxa de erro e custo divergem do real conforme o usuário usa a feature.

### Infraestrutura de Redis já existente

O projeto já tem Redis configurado e em uso:

| Componente | Arquivo | Uso atual |
|---|---|---|
| `redis>=5,<6` | `apps/api/pyproject.toml` | client instalado |
| `redis_url()` | `apps/api/app/config.py:51` | lê `REDIS_URL` do env |
| `RateLimiterBackend` | `apps/api/app/domain/services/rate_limit_service.py` | sliding-window de rate limit |
| `redis:7-alpine` | `docker-compose.yml` | service já declarado |
| `REDIS_URL: redis://redis:6379/0` | `docker-compose.yml` | env já injetado no container `api` |

O Redis está disponível mas **não é usado como broker de filas** — só como key-value
store para contadores de rate limit.

### Por que `arq` e não Celery ou RQ

| Lib | Pro | Contra | Decisão |
|---|---|---|---|
| **arq** | async-first, encaixa em FastAPI, broker Redis simples, sem deps extras além do client já presente | menos maduro que Celery, docs menores | **Escolhido** |
| **rq** | simples, síncrono, fácil de debugar | síncrono em contexto async, requer processos separados por queue | alternativa válida se arq travar |
| **Celery** | battle-tested, ecossistema amplo | overhead de config, Kombu como dep, configuração trabalhosa para projeto pequeno | descartado |

Decisão §1-A: usar `arq` como runtime de worker. Requer `arq>=0.26` (suporte a `redis>=5`).

---

## 2. Objetivo

Implementar a feature de reexecução de trace (`rerun`) de forma honesta:

1. A rota `POST /v1/traces/{id}/rerun` cria o placeholder **e** enfileira um job real.
2. Um processo worker separado (`arq` worker) pega o job, lê o span LLM original,
   reexecuta a chamada ao provider, e faz ingest do resultado no trace placeholder.
3. O trace placeholder transita `queued → running → completed | failed`.
4. A UI já consulta o trace por ID — nenhuma mudança visual é necessária além de
   tratar os novos valores de `metadata.replay_status`.

Não-objetivos desta spec:
- Suporte a rerun de traces sem span LLM (sem chamada ao provider).
- Interface de gerenciamento de jobs (queue dashboard, retry manual via UI).
- Múltiplas filas ou prioridades.
- Suporte a providers além do já usado pelo projeto.

---

## 3. Schema de dados

### 3.1 `metadata.replay_*` no `Trace` (sem migration)

O `Trace.metadata_json` (coluna `metadata`, tipo `JSON`) já existe. Nenhum novo campo
de banco é necessário para o MVP — o tracking de estado vive no próprio JSON do trace.

```
metadata = {
    "replay_of":       "<original_trace_id>",  # já existe hoje
    "replay_status":   "queued" | "running" | "completed" | "failed",
    "replay_error":    "<mensagem>" | null,
    "rerun_model":     "<override de modelo>" | null,
    "rerun_variables": { ... } | null,
    "replay_started_at": "<iso8601>" | null,
    "replay_finished_at": "<iso8601>" | null,
}
```

Transições de estado:
```
(rota rerun_trace cria placeholder)  →  "queued"
(worker pega o job)                  →  "running"
(worker conclui com sucesso)         →  "completed"
(worker falha após retries)          →  "failed"
```

### 3.2 Schema Pydantic atualizado (`apps/api/app/schemas.py`)

`TraceRerunOut` existe. Adicionar campos opcionais sem breaking change:

```python
class TraceRerunOut(BaseModel):
    new_trace_id: str
    status: str                    # "queued" (único valor nesta fase)
    replay_status: str = "queued"  # espelha metadata.replay_status
```

---

## 4. Plano de execução por fase

### Fase A — Infraestrutura da fila — **✅ IMPLEMENTADO (2026-05-21)**

Status: dependency `arq>=0.26,<1` adicionada; `worker_concurrency()` em `config.py`; módulo `app/workers/` criado com `settings.py` (functions=[], on_startup carrega `db_session_factory`, RedisSettings via `REDIS_URL`). Serviço `worker` adicionado em `docker-compose.yml` e `docker-compose.prod.yml` (prod ganhou também o serviço `redis` com healthcheck). Testes: `tests/test_worker_settings.py` valida import limpo, env override de concurrency, e parsing de `REDIS_URL`. Suite cheia: 310 passed. `python -m arq app.workers.settings.WorkerSettings --check` carrega settings sem erro e tenta conectar ao Redis (falha esperada sem container ativo).



**Escopo:** adicionar `arq` como dependência, configurar worker settings, adicionar
service `worker` no docker-compose. Sem lógica de negócio.

**Arquivos tocados:**

```
apps/api/pyproject.toml
apps/api/app/config.py
apps/api/app/workers/__init__.py          (novo — vazio)
apps/api/app/workers/settings.py          (novo)
docker-compose.yml
docker-compose.prod.yml
```

**`pyproject.toml` — adicionar dep:**
```toml
[project]
dependencies = [
    ...
    "arq>=0.26,<1",
]
```

**`apps/api/app/config.py` — novo getter:**
```python
def worker_concurrency() -> int:
    return _positive_int("EVALOPS_WORKER_CONCURRENCY", 4)
```

**`apps/api/app/workers/settings.py` — WorkerSettings mínimo:**
```python
from arq import cron
from app.config import redis_url, worker_concurrency

async def startup(ctx: dict) -> None:
    from app.db import SessionLocal
    ctx["db_session_factory"] = SessionLocal

async def shutdown(ctx: dict) -> None:
    pass

class WorkerSettings:
    functions = []          # populado na Fase B
    redis_settings = None   # arq usa REDIS_URL via env ou setter abaixo
    max_jobs = worker_concurrency()
    on_startup = startup
    on_shutdown = shutdown
```

**`arq` usa `REDIS_URL` do env diretamente** quando `redis_settings` é `None` com
`redis_url` exportado pelo módulo. Alternativa: usar `arq.connections.RedisSettings.from_dsn(redis_url())`.

**`docker-compose.yml` — service worker:**
```yaml
  worker:
    image: python:3.12-slim
    working_dir: /workspace
    volumes:
      - ./apps/api:/workspace
    environment:
      APP_ENV: local
      LOG_LEVEL: INFO
      DATABASE_URL: postgresql+asyncpg://evalops:evalops@postgres:5432/evalops
      REDIS_URL: redis://redis:6379/0
    command: >
      sh -c "pip install --no-cache-dir -e . &&
             python -m arq app.workers.settings.WorkerSettings"
    depends_on:
      - postgres
      - redis
```

**`docker-compose.prod.yml`** — mesmo padrão, imagem fixada e sem `--reload`.

**Teste da Fase A:**
```bash
docker compose up worker
# deve sair: "Starting worker for functions [] on redis://redis:6379/0"
```

**Critério de done:**
- Worker sobe sem erro.
- `WorkerSettings.functions` vazia — sem trabalho real ainda.

---

### Fase B — Worker de replay — **✅ IMPLEMENTADO (2026-05-21)**

Status: `app/workers/replay_worker.py` criado com:
- `_load_trace_or_fail` / `_find_primary_llm_span` (filtra `type in ("llm_call","llm")` OR `name ilike "llm.%"`, ordena por `started_at` asc)
- `_build_messages` aplica substituição jinja2 com `{{var_name}}` (decisão §B-2); tolera entries não-dict e content ausente
- `_call_provider` envolve `llm_judge.call_llm` em `asyncio.to_thread`; tokens via `estimate_tokens` (sync call retorna só texto); custo via `compute_cost_usd`
- `_ingest_replay_result` cria novo `Span` no placeholder + atualiza totais + commita
- `_set_replay_status` grava `replay_status`, `replay_started_at`, `replay_finished_at`, `replay_error`
- Exceptions do provider caem em `failed` com `reason=ExceptionClassName` (decisão §B-1: sem propagar)

`WorkerSettings.functions = [replay_trace]`.

Testes em `tests/test_replay_worker.py` (6 testes): happy path → completed; sem span LLM → failed com `no_llm_span_found`; substituição jinja `{{nome}}→Alice`; override de modelo via `rerun_model`; erro do provider → failed; `_build_messages` lida com entries inválidas. Suite: 316 passed.



**Escopo:** implementar a função `replay_trace` que o worker executa. Lê os spans LLM
do trace original, reexecuta a chamada ao provider, e faz ingest do resultado no
trace placeholder.

**Arquivos tocados:**
```
apps/api/app/workers/replay_worker.py     (novo)
apps/api/app/workers/settings.py          (atualizar functions=[])
apps/api/app/infra/llm/                   (verificar se existe client reutilizável)
apps/api/tests/test_replay_worker.py      (novo)
```

**Estrutura de `replay_worker.py`:**

```python
"""Worker function: replay_trace.

Reads the primary LLM span from the original trace, calls the provider,
and ingests the response into the placeholder trace created by rerun_trace.
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("evalops.worker.replay")


async def replay_trace(ctx: dict, original_trace_id: str, new_trace_id: str) -> dict:
    db_factory = ctx["db_session_factory"]

    with db_factory() as db:
        # 1. Carregar trace original e placeholder
        original = _load_trace_or_fail(db, original_trace_id)
        placeholder = _load_trace_or_fail(db, new_trace_id)

        # 2. Marcar como running
        _set_replay_status(db, placeholder, "running")

        # 3. Extrair span LLM primário
        llm_span = _find_primary_llm_span(db, original.id)
        if llm_span is None:
            _set_replay_status(db, placeholder, "failed",
                               error="no_llm_span_found")
            return {"status": "failed", "reason": "no_llm_span_found"}

        # 4. Chamar provider
        model = placeholder.metadata_json.get("rerun_model") or llm_span.model
        variables = placeholder.metadata_json.get("rerun_variables") or {}
        messages = _build_messages(llm_span, variables)

        result = await _call_provider(provider=llm_span.provider, model=model,
                                      messages=messages)

        # 5. Ingest resultado no placeholder
        _ingest_replay_result(db, placeholder, llm_span, result)
        _set_replay_status(db, placeholder, "completed")

    return {"status": "completed", "new_trace_id": new_trace_id}
```

**Funções auxiliares a implementar (mesmas responsabilidades, métodos privados):**

| Função | Responsabilidade |
|---|---|
| `_load_trace_or_fail(db, trace_id)` | Lê `Trace` ou lança `ValueError` se não encontrado |
| `_find_primary_llm_span(db, trace_id)` | Busca `Span` com `type="llm"` ou `name like "llm.%"` ordenado por `started_at` ASC, retorna o primeiro ou `None` |
| `_build_messages(span, variables)` | Extrai `span.messages_in`, substitui variáveis do dict `variables` (formato `{{var_name}}`), retorna lista de mensagens pronta para o provider |
| `_call_provider(provider, model, messages)` | Dispara chamada async ao provider via o client em `apps/api/app/infra/llm/`; retorna `ProviderResult(messages_out, tokens_in, tokens_out, cost_usd, duration_ms)` |
| `_ingest_replay_result(db, placeholder, original_span, result)` | Cria novo `Span` no placeholder, atualiza `placeholder.status="ok"`, `duration_ms`, `total_tokens_*`, `total_cost_usd` |
| `_set_replay_status(db, trace, status, error=None)` | Atualiza `trace.metadata_json["replay_status"]`, `replay_error`, timestamps; commita |

**Verificação antes de implementar `_call_provider`:**
Inspecionar `apps/api/app/infra/llm/` para reutilizar o client existente. Se não
existir client reutilizável, avaliar criar `LLMClient` mínimo como step separado
antes desta fase.

**Atualizar `settings.py`:**
```python
from app.workers.replay_worker import replay_trace

class WorkerSettings:
    functions = [replay_trace]
    ...
```

**Teste unitário (mock do provider e DB):**
```python
# test_replay_worker.py
async def test_replay_trace_transitions_to_completed(mock_db, mock_provider):
    # arrange: original trace com span LLM, placeholder em "queued"
    # act: await replay_trace(ctx, original_trace_id, new_trace_id)
    # assert: placeholder.metadata_json["replay_status"] == "completed"
    # assert: mock_provider chamado com messages_in do span original
    # assert: novo Span criado no placeholder

async def test_replay_trace_no_llm_span_fails_gracefully(mock_db):
    # trace sem span LLM → status "failed", reason "no_llm_span_found"
    # assert: sem exception propagada para fora

async def test_replay_trace_variables_substituted(mock_db, mock_provider):
    # span com mensagem "Olá {{nome}}", variables={"nome": "Alice"}
    # assert: provider recebe "Olá Alice"
```

**Critério de done:**
- `pytest apps/api/tests/test_replay_worker.py` verde.
- Worker sobe e função aparece no log de startup do arq.

---

### Fase C — Rota backend: enfileirar o job real

**Escopo:** modificar `rerun_trace` em `routes_trace_actions.py` para usar `arq` e
enfileirar o job após criar o placeholder. O contrato externo da rota não muda
(`TraceRerunOut` já retorna `new_trace_id` e `status`).

**Arquivo tocado:**
```
apps/api/app/api/routes_trace_actions.py:291-330
```

**Mudança principal:**

```python
# ── antes ──────────────────────────────────────────────────────────────────
db.add(new_trace)
db.commit()
return {"new_trace_id": new_trace.id, "status": "queued"}

# ── depois ─────────────────────────────────────────────────────────────────
db.add(new_trace)
db.commit()

# enfileirar job assíncrono
from arq import create_pool
from arq.connections import RedisSettings
from app.config import redis_url

redis = await create_pool(RedisSettings.from_dsn(redis_url()))
await redis.enqueue_job(
    "replay_trace",
    original_trace_id=trace.id,
    new_trace_id=new_trace.id,
)
await redis.aclose()

return {"new_trace_id": new_trace.id, "status": "queued"}
```

**Consideração de pool Redis:**
Criar o pool a cada request é caro. O padrão recomendado é:
- Inicializar o pool no startup da aplicação FastAPI (`lifespan` context manager em `apps/api/app/main.py`).
- Expor via `app.state.arq_pool` ou via `Depends`.
- Fechar no shutdown.

Isso é uma decisão de arquitetura a tomar na implementação — a spec não prescreve
a forma exata de lifecycle do pool para não over-engineer.

**Teste de integração:**
```python
# test_rerun_trace_actually_enqueues_worker.py
async def test_rerun_enqueues_job(client, mock_arq_pool):
    # POST /v1/traces/{id}/rerun
    # assert: mock_arq_pool.enqueue_job chamado com "replay_trace"
    # assert: args incluem original_trace_id e new_trace_id corretos
    # assert: response status 200, body tem new_trace_id e status "queued"

async def test_rerun_trace_redis_unavailable_returns_503(client, broken_redis):
    # Redis indisponível → 503 com mensagem "replay_unavailable"
    # Decisão §C-1: fail-closed (não criar trace fantasma sem enfileirar)
```

Decisão §C-1: se o Redis estiver indisponível no momento do `rerun`, a rota retorna
`503 Service Unavailable` com `{"detail": "replay_unavailable"}`. **Não** cria o
placeholder sem job — preferível falhar visivelmente a criar lixo silencioso.

**Critério de done:**
- Teste de enfileiramento verde.
- `GET /v1/traces/{new_trace_id}` mostra `status="partial"` enquanto o worker processa e `status="ok"` após conclusão.

---

### Fase D — Frontend

**Escopo:** mínimo. A UI já consulta o trace por ID após receber `new_trace_id` —
não há mudança visual estrutural necessária. Apenas tratar os novos valores de
`metadata.replay_status` para dar feedback mais preciso ao usuário.

**Arquivos tocados:**
```
apps/web/app/o/[org]/p/[project]/traces/[trace]/page.tsx
apps/web/lib/types.ts  (verificar se TraceMetadata cobre replay_status)
```

**Mudanças:**

1. **Banner pós-rerun** (já existe em `page.tsx:123-136`):
   - Hoje: "Reexecução enfileirada · ver trace".
   - Com a spec: pode manter igual — o trace existe e tem status real agora.
   - Melhoria opcional: mostrar badge dinâmico `queued | running | completed | failed`
     baseado em `trace.metadata.replay_status` quando `trace.metadata.replay_of` está
     presente.

2. **Polling** (opcional, fase posterior):
   - Quando `metadata.replay_status === "running"`, fazer polling leve no trace
     (`GET /v1/traces/{id}` a cada 3s) até `completed | failed`.
   - O padrão de polling já existe no projeto em
     `apps/web/app/o/[org]/p/[project]/traces/page.tsx` para trace status —
     reutilizar o mesmo mecanismo.

3. **Empty state do trace fantasma** — não existe mais após Fase C, logo a Fase D
   pode ser implementada sem urgência.

**Critério de done:**
- Banner não mostra mais "Reexecução enfileirada" para trace eternamente `partial`.
- Badge de `replay_status` visível no detalhe do trace (se implementado).

---

### Fase E — Testes e observabilidade

**Escopo:** testes de integração end-to-end e logging estruturado no worker.

**Teste e2e (Playwright `apps/web/e2e/smoke.spec.ts`):**
```ts
test("rerun trace creates real completed trace", async ({ page }) => {
  // 1. Criar trace via SDK (ou API direta)
  // 2. Navegar para o detalhe do trace
  // 3. Clicar em "Reexecutar"
  // 4. Aguardar redirect para novo trace
  // 5. Aguardar polling até metadata.replay_status === "completed" (timeout 30s)
  // 6. Assert: trace com status "ok", tokens > 0, cost_usd > 0
});
```

**Logging no worker (`replay_worker.py`):**
```python
logger.info("replay.started",  extra={"trace_id": new_trace_id, "original": original_trace_id})
logger.info("replay.completed", extra={"trace_id": new_trace_id, "duration_ms": ...})
logger.error("replay.failed",   extra={"trace_id": new_trace_id, "reason": ...})
```

**Observabilidade mínima (sem dashboard):**
- `metadata.replay_status` consultável via `GET /v1/traces/{id}` — suficiente para
  debug via API.
- Logs estruturados no worker capturados pelo `docker compose logs worker`.

**Critério de done:**
- Teste e2e verde com worker rodando em docker-compose.
- Sem trace com `status="partial"` e `duration_ms=0` após o fluxo completo.

---

## 5. Decisões registradas

| Código | Decisão |
|---|---|
| §1-A | Usar `arq>=0.26` como runtime de worker (Redis como broker). |
| §1-B | Tracking de estado do job via `metadata.replay_status` no próprio `Trace` — sem tabela nova de jobs para o MVP. |
| §C-1 | Se Redis indisponível no momento do `rerun`, retornar `503` — não criar placeholder sem job enfileirado. |
| §C-2 | Pool arq inicializado no `lifespan` do FastAPI — decisão exata de lifecycle fica para a implementação. |
| §B-1 | Se o trace original não tiver span LLM, o replay marca `failed` com `reason="no_llm_span_found"` — sem propagação de exception para o worker framework. |
| §B-2 | Substituição de variáveis usa delimitador `{{var_name}}` — mesmo padrão que os prompts do projeto (verificar em `docs/10-prompt-and-model-versioning.md` antes de implementar). |

---

## 6. Ordem de execução recomendada

```
Fase A  (infra)     ~2h
Fase B  (worker)    ~4h  ← verificar apps/api/app/infra/llm/ antes de iniciar
Fase C  (rota)      ~2h
Fase D  (front)     ~1h  ← pode ser adiada
Fase E  (testes)    ~2h
                   ─────
Total estimado      ~11h de trabalho
```

**Dependências entre fases:**
- B depende de A (worker settings precisa existir para registrar a função).
- C depende de B (enfileira função que só existe após B).
- D e E são independentes entre si, mas dependem de C.

---

## 7. Referências

- Bug #1 original: `docs/audits/tentativa_refactor-code-review-2026-05-21.md#-1-post-v1tracesidrerun-cria-trace-fantasma-sem-enfileirar-worker`
- Infraestrutura Redis existente: `apps/api/app/domain/services/rate_limit_service.py`
- Config Redis: `apps/api/app/config.py:51-62`
- Rota atual (stub): `apps/api/app/api/routes_trace_actions.py:291-330`
- Client LLM a verificar: `apps/api/app/infra/llm/`
- Padrão de polling frontend: `apps/web/app/o/[org]/p/[project]/traces/page.tsx`
- Modelo `Span` (campos `messages_in`, `model`, `provider`): `apps/api/app/models.py:117-145`
- Modelo `Trace` (`metadata_json`): `apps/api/app/models.py:77-103`
