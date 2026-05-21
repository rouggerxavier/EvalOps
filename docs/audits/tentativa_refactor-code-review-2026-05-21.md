# Code Review — branch `tentativa_refactor` (2026-05-21)

> Escopo: 28 commits a partir da base `3f42e7b` + plano `docs/plans/refatoração_identica.md`.
> Foco: bugs reais (usuário-frágil, dado errado, feature anunciada-mas-quebrada), não nitpicks.
> Reviewer: code-review automatizado via agent-framework (diff-reviewer + security-privacy-audit).

---

## Sumário executivo

| # | Severidade | Tema | Arquivo principal |
|---|---|---|---|
| 1 | 🔴 quebra feature | `POST /traces/{id}/rerun` não enfileira nada — **adiado** (spec em `docs/plans/evalops-async-worker-replay-spec.md`) | `apps/api/app/api/routes_trace_actions.py` |
| 2 | ✅ corrigido | Página de Exports integra `listExports` do servidor | `apps/web/app/o/[org]/p/[project]/exports/page.tsx` |
| 3 | 🔴 quebra feature | Topbar bell + workspace switcher não montados | `apps/web/components/EvoTopbar.tsx` |
| 4 | 🔴 quebra feature | Tabs "Lentos" e "RAG" filtram só página atual | `apps/web/app/o/[org]/p/[project]/traces/page.tsx` |
| 5 | 🟠 perf / scalability | `GET /prompts/{id}/usage` faz full-table-scan | `apps/api/app/api/routes_phase5.py` |
| 6 | 🟠 perf | `list_traces` carrega todos `EvaluationRun`s dos 50 traces | `apps/api/app/api/routes.py` |
| 7 | 🟠 dado errado | p95 de ingestão off-by-one | `apps/api/app/api/routes.py` |
| 8 | 🟡 frágil | `mark-read` com `ids=[]` marca tudo | `apps/api/app/api/routes.py` |
| 9 | 🟡 frágil | PATCH `/projects/{id}` muta `description` sem mudança real | `apps/web/lib/actions.ts` |
| 10 | 🟡 frágil | Overview perde traces `partial` no card de atenção | `apps/web/app/o/[org]/p/[project]/page.tsx` |
| 11 | 🟡 UX | Lista de traces sem botão "página anterior" | `apps/web/app/o/[org]/p/[project]/traces/page.tsx` |
| 12 | 🟡 dado errado | Compare-spans com fallback de timezone frágil | `apps/api/app/api/routes_trace_actions.py` |
| 13 | 🟡 dado fabricado | RAG endpoint fabrica claim counts via `support_rate * 10` | `apps/api/app/api/routes_trace_actions.py` |
| 14 | 🟡 contrato | `next_cursor` retornado em exports listing sem consumidor | `apps/api/app/api/routes_phase6.py` |
| 15 | 🔵 security | Trace flag/rerun sem audit log | `apps/api/app/api/routes_trace_actions.py` |
| 16 | 🔵 security | `GET /traces/{id}/rag` ignora `trace.redacted` | `apps/api/app/api/routes_trace_actions.py` |
| 17 | 🔵 perf/dos | `list_organization_members` sem paginação | `apps/api/app/api/routes.py` |
| 18 | 🟡 idempotência | `bulk_flag_traces` permite duplo-flag | `apps/api/app/api/routes_trace_actions.py` |

Itens críticos (🔴): 4. Bloqueiam merge.
Itens de scalability (🟠): 3. Bloqueiam produção real.
Itens de UX/contrato (🟡): 8. Bloqueiam UAT.
Itens de security (🔵): 3. Bloqueiam release público.

---

## 🔴 1. `POST /v1/traces/{id}/rerun` cria trace-fantasma sem enfileirar worker

### Onde
`apps/api/app/api/routes_trace_actions.py:291-330`

### O que está errado
A rota responde `{ "new_trace_id": "...", "status": "queued" }` mas **não enfileira nada**. Apenas cria um `Trace` novo com `status="partial"`, `duration_ms=0`, todos os contadores zerados, e marca `metadata.replay_of = original_trace_id`. Nenhum job é submetido ao worker.

```python
new_trace = Trace(
    id=new_id("tr"),
    ...
    status="partial",
    started_at=now,
    ended_at=now,
    duration_ms=0,
    total_tokens_in=0,
    total_tokens_out=0,
    total_cost_usd=0,
    ...
)
db.add(new_trace)
db.commit()
return {"new_trace_id": new_trace.id, "status": "queued"}
```

### Impacto no usuário
- UI mostra banner "Reexecução enfileirada" + link para o trace fantasma (`apps/web/app/o/[org]/p/[project]/traces/[trace]/page.tsx:123-136`).
- Usuário clica no link → trace eternamente em `partial` com zero dados.
- Cada clique no botão "Reexecutar" cria mais um stub. Trace list enche de fantasmas que diluem p95, taxa de erro e contagem de traces.
- Métrica "Saúde do SDK" e "Custo por modelo" começam a divergir do realidade conforme o usuário usa a feature.

### Quebra do plano
Plan §4.6 explícito:
> "Cria job assíncrono que reexecuta o trace original com mesmo prompt/inputs. Implementação: enfileira no worker existente (mesmo padrão do `experiment_runner`), usa `prompt_version_ref` + `metadata.input` do trace original. Marca novo trace com `metadata.replay_of = original_trace_id`."

Só a parte do `replay_of` foi feita.

### Como corrigir

> **Caminho escolhido: Opção A — implementar via `arq` + Redis (já disponível no projeto).**
>
> Spec completa com plano de execução por fase em:
> `docs/plans/evalops-async-worker-replay-spec.md`
>
> Resumo das fases:
> - **Fase A** (~2h): adicionar `arq>=0.26` ao `pyproject.toml`, criar `apps/api/app/workers/settings.py`, adicionar service `worker` no `docker-compose.yml`.
> - **Fase B** (~4h): implementar `apps/api/app/workers/replay_worker.py` — lê span LLM original, reexecuta no provider, ingesta resultado no placeholder.
> - **Fase C** (~2h): modificar `rerun_trace` em `routes_trace_actions.py:291-330` para enfileirar job via `arq` após criar placeholder. Se Redis indisponível → `503`, não cria trace fantasma.
> - **Fase D** (~1h): atualizar badge de `metadata.replay_status` no detalhe do trace (pode ser adiada).
> - **Fase E** (~2h): testes e2e + logging estruturado.
>
> Total estimado: ~11h. Redis já está disponível em `docker-compose.yml` e em uso no projeto (`rate_limit_service.py`). Tracking de estado via `metadata.replay_status` no próprio `Trace` — sem nova tabela.

**A. (Não usar) Implementação ad-hoc sem spec:**
Descartada — sem plano de lifecycle do pool arq, sem decisão de fail policy se Redis cair.

**B. Marcar como dev-only e esconder no UI:**
Descartada — mantém o stub no banco, polui métricas se alguém habilitar.

**C. Remover a feature:**
Alternativa válida se a spec A for adiada indefinidamente. Drop da rota, do action, do botão.

### Como evitar regressão
Adicionar teste de integração que verifica que `metadata.replay_status` chega em `"completed"` ou `"failed"` em até X segundos, ou que o worker `replay_trace` foi chamado (mock).

---

## ✅ 2. Página de Exports não usa o endpoint `GET /projects/{id}/exports` — **CORRIGIDO**

> **Status:** corrigido em `4fc50f3` → commit `<próximo>` (branch `claude/repository-access-X2Zcv`)

### Onde
- Frontend: `apps/web/app/o/[org]/p/[project]/exports/page.tsx`
- Backend: `apps/api/app/api/routes_phase6.py`
- Wrapper: `apps/web/lib/api.ts:422` (`listExports`)

### O que estava errado
A página construía a lista apenas com IDs presentes no query string da URL. O wrapper `listExports(projectId)` existia mas **não era chamado**.

### O que foi corrigido
1. `listExports(resolvedProject.project_id)` adicionado no `Promise.all` da página.
2. Resultado do servidor mesclado com `knownIds` (dedup por `id`): server é fonte primária, `knownIds` complementa com IDs recém-criados ainda não listados.
3. Coluna "Tamanho" marcada como `—` (sem `file_size_bytes` no model atual — campo pode ser adicionado em migration futura).
4. Card "Contrato atual" removido (dizia que não existia endpoint de listagem — desatualizado).
5. Empty state e summary card atualizados para refletir listagem real do servidor.

### Pendências deixadas para depois
- Coluna "Tamanho" mostra `—` — `file_size_bytes` não existe no model `ExportJob`. Requer migration.
- Teste e2e (criar 2 exports via API, verificar que aparecem na tabela) não foi adicionado nesta rodada.

---

## 🔴 3. Topbar bell + WorkspaceSwitcher montados como placeholder

### Onde
- `apps/web/components/EvoTopbar.tsx:104-122`
- `apps/web/components/ui/NotificationsBell.tsx` (criado mas órfão)
- `apps/web/components/ui/WorkspaceSwitcher.tsx` (criado mas órfão)

### O que está errado
O sino do topbar mostra literal:
```tsx
<div className="card__body">
  <div className="faint">Sem notificacoes novas.</div>
</div>
```

Nunca chama `/v1/projects/{id}/notifications`. `unread_count` retornado pelo backend é ignorado. O componente `NotificationsBell.tsx` existe, mas o único lugar que o referencia é o barrel `components/ui/index.ts:14`. Idem para `WorkspaceSwitcher`.

### Impacto no usuário
- Sino sempre vazio mesmo quando há eventos relevantes (rubrica publicada, key expirando, export concluído).
- Usuário não percebe que precisa olhar Keys quando uma chave expira em <7d (plan §3.5).
- Workspace switcher hardcoded mostra apenas o projeto atual; usuário com múltiplos projetos navega via URL.

### Quebra do plano
Plan §3.5:
> "Sino com badge + dropdown (`NotificationsBell.tsx`)"
> "Workspace switcher real (`WorkspaceSwitcher.tsx`): chama `/v1/me`, lista orgs e projects do usuário, navega para `/o/{org}/p/{project}`"

### Como corrigir
1. **Bell:**
   - Em `EvoTopbar.tsx`, importar `NotificationsBell` e substituir o bloco `<button>` + `notificationsOpen` dropdown.
   - Passar `notifications` e `unread_count` carregados via Server Component pai (provavelmente `layout.tsx` da rota `/o/[org]/p/[project]`).
   - `NotificationsBell` precisa de uma Server Action `markNotificationsReadAction` para chamar no `onOpen` ou em click do botão "Marcar todas".
   - Trocar dot fixo por badge com `unread_count`.
2. **WorkspaceSwitcher:**
   - Em `Sidebar.tsx` (ou `EvoTopbar.tsx`, conforme preview), montar o componente passando `orgs` e `projects` vindos de `/v1/me`.
   - Implementar combobox real (não só `<select>`) se o preview pedia isso.
3. Atualizar `apps/web/e2e/smoke.spec.ts` para asserir que o badge do sino aparece quando há `notifications.unread_count > 0`.

### Risco lateral
- `mark-read` empty-list bug (#8) precisa ser corrigido **antes** de o bell ser ligado, senão `<NotificationsBell>` com lista vazia ao abrir pode mandar `{ids: []}` e apagar tudo.

---

## 🔴 4. Tabs "Lentos" e "RAG" filtram só os 50 da página atual

### Onde
`apps/web/app/o/[org]/p/[project]/traces/page.tsx:38-62`

### O que está errado
```ts
const tabStatus = tab === "errors" ? "error" : tab === "partial" ? "partial" : qp.status;
const traces = await getTraces({
  projectId, status: tabStatus,
  name: tab === "rag" ? "rag." : qp.name,
  limit: 50, cursor: qp.cursor,
});

const displayRows =
  tab === "slow"
    ? rows.filter((t) => t.duration_ms > 2000)
    : tab === "rag"
    ? rows.filter(isTraceRagCandidate)
    : rows;
```

Tab `slow` não tem filtro server-side: a query é feita sem `duration_gt` (o backend não suporta), e o filtro acontece em JS sobre os 50 rows.

Tab `rag` envia `name: "rag."` mas isso é um match parcial frágil (depende de naming convention dos clientes) + `isTraceRagCandidate` adicional no cliente.

Os `counts` exibidos no chip de cada tab também são contagens da página atual (`counts.errors = rows.filter(...).length`), não totais do projeto.

### Impacto no usuário
- Projeto com 1000 traces lentos mas nenhum nas últimas 50 entradas → tab "Lentos" empty state. Bug invisível: parece que não há traces lentos.
- Tab "RAG" mostra `(0)` mesmo quando o projeto é 100% RAG, porque `name` não bate com `"rag."`.
- Contagens das tabs mudam conforme o usuário pagina. UX inconsistente.

### Como corrigir
1. **Backend (`routes.py` `list_traces`):**
   - Adicionar query param `duration_gt: int | None = Query(None, ge=0)` e aplicar `Trace.duration_ms > duration_gt`.
   - Adicionar `rag: bool | None = Query(None)` que aplica `Trace.name.like("rag.%") | Trace.tags["is_rag"].as_boolean() == True` (ou critério padronizado).
2. **Frontend:**
   - Tab "Lentos" → `getTraces({ ..., duration_gt: 2000 })`.
   - Tab "RAG" → `getTraces({ ..., rag: true })`.
   - Remover `displayRows` client-side.
3. **Counts globais:**
   - Backend novo endpoint `GET /projects/{id}/traces/segments` retornando `{ all, errors, partial, slow, rag }` para a janela atual (env + name filter aplicados).
   - Frontend chama esse endpoint em paralelo com `getTraces` e popula chips com totais reais.
4. **Empty state honesto** quando a tab tem 0 globalmente.

### Como evitar regressão
Teste backend: criar 60 traces lentos, paginar com `limit=10`, conferir que tab `slow` no chip reporta 60 e que `?duration_gt=2000` retorna eles em todas as páginas. Frontend e2e: criar 5 RAG e 5 não-RAG, conferir contagem.

---

## 🟠 5. `GET /v1/prompts/{id}/usage` faz full-table-scan + sub-conta

### Onde
`apps/api/app/api/routes_phase5.py:200-219`

### O que está errado
```python
metadata_matches = (
    db.query(Trace)
    .filter(Trace.project_id == prompt.project_id, Trace.deleted_at.is_(None))
    .order_by(Trace.created_at.desc())
    .all()                       # ← sem LIMIT
)
for trace in metadata_matches:
    ...
    meta_ref = meta.get("prompt_ref") or meta.get("prompt_version_ref") or meta.get("prompt_id")
    if isinstance(meta_ref, str) and meta_ref in refs:
        rows_by_trace.setdefault(trace.id, {...})

traces = sorted(rows_by_trace.values(), key=lambda row: row["used_at"], reverse=True)[:limit]
return {"prompt_id": prompt.id, "usage_count": len(rows_by_trace), "traces": traces}
```

Dois problemas:
1. **Sem LIMIT**: carrega TODOS os traces do projeto na memória do worker para filtrar por `metadata.prompt_ref` em Python. Projeto com 1M traces = OOM.
2. **`usage_count` mente**: o valor é `len(rows_by_trace)` mas como o primeiro passo (span_rows) tem `LIMIT limit` e o segundo passo só preenche o que falta com `setdefault` quando `len(rows_by_trace) < limit`, prompts populares retornam `usage_count = limit` mesmo tendo 100k usos reais.

### Plan §4.14 prescreveu o índice que falta
```
2026XXXXXXXX_add_prompt_ref_index.py (índice em traces.metadata->>'prompt_ref' para suportar §4.10)
```

Conferido em `apps/api/alembic/versions/`: existe `0001..0005`, **migração de índice não foi criada**.

### Como corrigir
1. **Migration nova `0006_prompt_ref_index.py`**:
   ```python
   # Postgres
   op.execute(
       "CREATE INDEX IF NOT EXISTS ix_traces_metadata_prompt_ref "
       "ON traces ((metadata_json->>'prompt_ref'))"
   )
   ```
   Para SQLite (dev/test), generated column index ou skip — documentar.
2. **Refactor da query**:
   ```python
   metadata_matches = (
       db.query(Trace)
       .filter(
           Trace.project_id == prompt.project_id,
           Trace.deleted_at.is_(None),
           or_(
               Trace.metadata_json["prompt_ref"].astext.in_(refs),
               Trace.metadata_json["prompt_version_ref"].astext.in_(refs),
               Trace.metadata_json["prompt_id"].astext.in_(refs),
           ),
       )
       .order_by(Trace.created_at.desc())
       .limit(limit)
       .all()
   )
   ```
3. **Contagem honesta**: separar query de count vs query de listing:
   ```python
   usage_count = (
       db.query(func.count(distinct(Trace.id)))
       .filter(... mesmos critérios ...)
       .scalar() or 0
   )
   ```
4. Schema `PromptUsageOut`: adicionar `usage_count_truncated: bool` para sinalizar se houve mais que `limit`.

### Como evitar regressão
Teste de carga: criar 5k traces com `metadata.prompt_ref` apontando para o mesmo prompt; conferir que `usage_count = 5000` e a query roda em <500ms.

---

## 🟠 6. `list_traces` carrega todos `EvaluationRun`s para popular `last_score`

### Onde
`apps/api/app/api/routes.py:443-458` (commit `3083e31`)

### O que está errado
```python
runs = (
    db.query(EvaluationRun)
    .filter(EvaluationRun.trace_id.in_(trace_ids))
    .order_by(EvaluationRun.trace_id.asc(), EvaluationRun.created_at.desc())
    .all()
)
for run in runs:
    if run.trace_id not in last_scores:
        last_scores[run.trace_id] = float(run.aggregate_score) if run.aggregate_score is not None else None
```

Carrega **todos** os EvaluationRuns dos 50 traces. Trace com 30 runs históricos → 30 linhas carregadas em memória, mas só a mais recente é usada.

### Plan §9 já alertou
> "`score` em listagem de traces deixa query lenta — Mitigação: subquery com `LIMIT 1` por trace + índice composto em `evaluation_runs (trace_id, created_at desc)`"

Implementação ignorou ambos.

### Como corrigir
**Postgres (LATERAL JOIN):**
```sql
SELECT t.*, latest_eval.aggregate_score AS last_score
FROM traces t
LEFT JOIN LATERAL (
  SELECT er.aggregate_score
  FROM evaluation_runs er
  WHERE er.trace_id = t.id
  ORDER BY er.created_at DESC
  LIMIT 1
) latest_eval ON true
WHERE ...
```

**SQLAlchemy portátil (window function):**
```python
from sqlalchemy import select, func, and_

ranked = (
    select(
        EvaluationRun.trace_id,
        EvaluationRun.aggregate_score,
        func.row_number()
            .over(
                partition_by=EvaluationRun.trace_id,
                order_by=EvaluationRun.created_at.desc(),
            )
            .label("rn"),
    )
    .where(EvaluationRun.trace_id.in_(trace_ids))
    .subquery()
)
last_scores_q = select(ranked.c.trace_id, ranked.c.aggregate_score).where(ranked.c.rn == 1)
last_scores = {row.trace_id: float(row.aggregate_score) if row.aggregate_score is not None else None
               for row in db.execute(last_scores_q)}
```

**Migration**:
```python
# 0007_evaluation_runs_index.py
op.create_index(
    "ix_evaluation_runs_trace_created",
    "evaluation_runs",
    ["trace_id", "created_at"],
    postgresql_using="btree",
)
```

### Como evitar regressão
Teste: criar trace com 100 runs; conferir que `GET /v1/traces?project_id=...` faz no máximo 2 queries (1 traces, 1 last_scores) e completa em <300ms.

---

## 🟠 7. p95 de ingestão off-by-one (sub-reporta)

### Onde
`apps/api/app/api/routes.py:328-334`

### O que está errado
```python
ingestion_latencies.sort()
if ingestion_latencies:
    p95_index = max(0, min(len(ingestion_latencies) - 1, int(0.95 * (len(ingestion_latencies) - 1))))
    p95 = ingestion_latencies[p95_index]
```

Para `len=20`, `int(0.95 * 19) = 18` → índice 18 → 90º percentil, não p95.

### Impacto
KPI "Saúde do SDK · p95" exposto na Overview fica otimista. Diagnóstico de problemas de ingestão atrasado.

### Como corrigir
```python
import math
n = len(ingestion_latencies)
p95_index = min(n - 1, max(0, math.ceil(0.95 * n) - 1))
p95 = ingestion_latencies[p95_index]
```

ou usar `statistics.quantiles(data, n=100)[94]` (Python 3.8+), ou portar a heurística NIST com interpolação.

### Como evitar regressão
Teste com lista determinística `[1..100]`: p95 deve ser ≥95.

---

## 🟡 8. `POST /notifications/mark-read` com `ids: []` marca TODAS

### Onde
`apps/api/app/api/routes.py:280-296`

### O que está errado
```python
query = db.query(Notification).filter(
    Notification.project_id == project.id, Notification.read_at.is_(None)
)
if payload.ids:                              # ← lista vazia é falsy
    query = query.filter(Notification.id.in_(payload.ids))
rows = query.all()
```

Quando frontend envia `{"ids": []}` (loop sobre seleção vazia, race de UI, "marcar todas" sem ids), o filtro de IDs **não** é aplicado e todas as não-lidas viram lidas.

### Impacto
Usuário perde o histórico de notificações sem ter interagido com cada uma. Pior: notificações de "key expirando" desaparecem sem nunca terem sido vistas.

### Como corrigir
**Opção A (recusar `[]`):**
```python
class NotificationMarkReadIn(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=200)
```
Pydantic já rejeita `[]`.

**Opção B (semântica explícita "marcar tudo"):**
```python
class NotificationMarkReadIn(BaseModel):
    ids: list[str] | None = None  # None = mark all
    mark_all: bool = False

# route:
if payload.ids is None and not payload.mark_all:
    raise HTTPException(400, "must specify ids or mark_all=true")
if payload.ids:
    query = query.filter(Notification.id.in_(payload.ids))
elif not payload.mark_all:
    return {"updated": 0}
```

**Opção C (mínimo viável):**
```python
if not payload.ids:
    return {"updated": 0}
query = query.filter(Notification.id.in_(payload.ids))
```

Recomendo **A** — bloqueia o erro no schema. Frontend nunca consegue enviar `[]`.

### Como evitar regressão
Teste `test_mark_read_empty_ids_is_rejected_with_422`.

---

## 🟡 9. PATCH `/projects/{id}` muta `description` mesmo sem mudança real

### Onde
- Frontend: `apps/web/lib/actions.ts:571-593`
- Backend: `apps/api/app/api/routes.py` `update_project`

### O que está errado
```ts
const description = String(formData.get("description") ?? "");
...
await patchProject(projectId, {
  name: name || undefined,
  description: formData.has("description") ? description : undefined,   // ← sempre true
  default_environment: defaultEnvironment || undefined,
});
```

`formData.has("description")` é **sempre** `true` (input está no form). Quando o projeto tem `description=null` e o usuário clica "Salvar" sem editar nada, action envia `description: ""`. Backend:
```python
if "description" in payload.model_fields_set and payload.description != project.description:
    changes["description"] = {"from": project.description, "to": payload.description}
    project.description = payload.description
```
`"" != None` → grava `""`, registra audit `"description changed null → ''"`.

### Impacto
- Audit trail sujo: muda do nada vira "alteração".
- Trigger de webhook/notificação eventual dispara falso-positivo.
- Diff visual em UI futura ficará "0 caracteres alterados".

### Como corrigir
**Frontend (`apps/web/lib/actions.ts`):**
```ts
const descriptionRaw = String(formData.get("description") ?? "");
const description = descriptionRaw.trim() === "" ? null : descriptionRaw;
...
await patchProject(projectId, {
  name: name || undefined,
  description,  // null preserva null no backend
  default_environment: defaultEnvironment || undefined,
});
```

**Backend (`routes.py`):**
```python
# normalizar
new_description = payload.description
if isinstance(new_description, str) and new_description.strip() == "":
    new_description = None

if new_description != project.description:
    changes["description"] = {"from": project.description, "to": new_description}
    project.description = new_description
```

Os dois lados normalizando reduz o risco. Adicionar teste.

### Como evitar regressão
Teste `test_patch_project_no_change_does_not_audit`.

---

## 🟡 10. Overview perde traces `partial` no card "Últimos com problema"

### Onde
`apps/web/app/o/[org]/p/[project]/page.tsx:121`

### O que está errado
```ts
getTraces({ projectId, limit: 4, status: "error", environment })
```

Plan §3.6.1 previa:
> "Últimos traces com problema (até 4): `getTraces({status: "error,partial", limit: 4})`"

Implementação envia só `"error"`. Traces em `partial` (timeout parcial, retry no meio, schema mismatch sem morrer) **não aparecem** no card de atenção.

### Como corrigir
Backend `list_traces` precisa aceitar status CSV ou repetição:
```python
status: list[str] | None = Query(None)
# ou
status: str | None = Query(None)  # aceitar "error,partial"
```

Já existe `Trace.status.in_(...)` em outras rotas. Ajustar `getTraces` wrapper:
```ts
export async function getTraces(opts: {
  ...
  status?: string | string[];
  ...
}): Promise<TraceListResponse> {
  const params = new URLSearchParams();
  ...
  if (opts.status) {
    const value = Array.isArray(opts.status) ? opts.status.join(",") : opts.status;
    params.set("status", value);
  }
  ...
}
```

Frontend:
```ts
getTraces({ projectId, limit: 4, status: ["error", "partial"], environment })
```

### Como evitar regressão
Teste e2e que cria 1 partial + 1 error e verifica que ambos aparecem no card.

---

## 🟡 11. Lista de traces sem botão "página anterior"

### Onde
`apps/web/app/o/[org]/p/[project]/traces/page.tsx:197-209`

### O que está errado
```tsx
<button type="button" className="btn btn--sm btn--ghost" disabled>
  ‹
</button>
{nextPageHref ? <Link ...>›</Link> : <button disabled>›</button>}
```

Botão `‹` **sempre disabled**. Usuário avança cursors, não consegue voltar.

### Como corrigir
Duas opções:

**A. Manter histórico no client (botão back do browser):**
- Trocar `<button disabled>` por `<Link href={browserBack}>` — não é trivial em RSC.
- Ou expor um stack em cookie/localStorage.

**B. Cursor bidirecional no backend (recomendado):**
- `list_traces` aceita `cursor_before: str | None` além de `cursor`.
- Frontend mantém `prev_cursor` em URL: `?cursor=...&prev=...` (cada navegação empilha o anterior em querystring).
- Botão `‹` link para `?cursor=prev_cursor`.

**C. Quick fix:**
- Botão `‹` link para a rota sem `?cursor=` (volta à página 1). Não é "anterior", mas dá saída.

### Como evitar regressão
Smoke test que navega ›, ›, ‹, ‹, ‹ e verifica que termina na primeira página.

---

## 🟡 12. Compare-spans com fallback de timezone frágil

### Onde
`apps/api/app/api/routes_trace_actions.py:352-354`

### O que está errado
```python
"started_delta_seconds": int((right.started_at - left.started_at).total_seconds())
if right.started_at.tzinfo == left.started_at.tzinfo
else int((right.started_at.replace(tzinfo=timezone.utc) - left.started_at.replace(tzinfo=timezone.utc)).total_seconds()),
```

Dois cenários:
- Ambos naive (mesma tzinfo `None`) → diff direto. OK.
- Ambos aware mesma tz → diff direto. OK.
- **Aware com offsets diferentes** (SDK gravou em `-03:00`, DB devolveu em UTC) → ternário entra no else, `.replace(tzinfo=timezone.utc)` **substitui** o offset sem ajustar → delta errado pelo gap de 3h.

### Como corrigir
```python
def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

started_delta_seconds = int((_to_utc(right.started_at) - _to_utc(left.started_at)).total_seconds())
```

Igual para `duration_delta_ms`, `ended_at`, etc — auditar todos os subtraídos.

### Como evitar regressão
Teste com dois traces criados em sessions com `tzinfo` diferentes.

---

## 🟡 13. RAG endpoint fabrica claim counts via `support_rate * 10`

### Onde
`apps/api/app/api/routes_trace_actions.py:236-245`

### O que está errado
```python
grounded = sum(1 for claim in claims if claim["grounded"])
ungrounded = sum(1 for claim in claims if not claim["grounded"])
if not claims:
    unsupported = int(_as_number(grounding_out.get("unsupported_claim_count") or meta.get("unsupported_claim_count")) or 0)
    support_rate = _as_number(grounding_out.get("support_rate") or finalize_out.get("support_rate") or meta.get("support_rate"))
    if support_rate is not None:
        grounded = int(round(support_rate * 10))      # ← inventa total de 10
        ungrounded = max(unsupported, 10 - grounded)
    else:
        ungrounded = unsupported
```

Quando o trace tem `support_rate=0.4` mas nenhum claim individual gravado, o endpoint inventa 4 grounded e 6 ungrounded. UI mostra "4 / 10 claims grounded" sem que existam 10 claims.

### Impacto
Dado fabricado vendido como fato em painel de auditoria. Em compliance/segurança LLM, isso vira evidência falsa.

### Como corrigir
**Não inventar.** Retornar `null`/`unknown` quando faltam dados:
```python
if not claims:
    if support_rate is not None:
        # mostra apenas a métrica derivada, sem inventar totais
        return {
            "support_rate": support_rate,
            "grounded_claims": None,
            "ungrounded_claims": None,
            "claims_unavailable": True,
            ...
        }
    grounded = ungrounded = None
```

Frontend (`RagPanel.tsx`, `traces/[trace]/page.tsx:225-233`) precisa exibir `—` ou "n/d" quando `null`.

### Como evitar regressão
Teste com trace que tem `support_rate=0.4` e sem claims → asserir que response retorna `grounded_claims=None`, não `4`.

---

## 🟡 14. `next_cursor` em `list_project_exports` sem consumidor

### Onde
`apps/api/app/api/routes_phase6.py` (commit `1fb86fe`)

### O que está errado
A rota aceita `limit` mas **não** aceita `cursor` como query param. Retorna `next_cursor: rows[-1].id` que nenhuma chamada consegue consumir. Pagination quebrada por construção.

### Como corrigir
1. Adicionar param `cursor: str | None = Query(None)` ao endpoint.
2. Aplicar filtro `if cursor: query.filter(ExportJob.id < cursor)` (combinado com `created_at` se necessário para evitar pular linhas).
3. Documentar em `docs/07-api-spec.md`.

(Bug fica latente até alguém usar `listExports` no frontend — ver bug #2.)

### Como evitar regressão
Teste que cria 60 exports, pagina com `limit=20`, espera 3 páginas distintas via `next_cursor`.

---

## 🔵 15. Ações de mutação de trace sem audit log

### Onde
`apps/api/app/api/routes_trace_actions.py:178-189, 269-288, 291-330`

### O que está errado
`flag_trace`, `bulk_flag_traces`, `rerun_trace` **não chamam** `record_audit`. `update_project` (commit `3083e31`) chama. Inconsistência: ações que alteram estado visível e criam recursos ficam invisíveis no audit log.

### Impacto
- Investigação pós-incidente impossível ("quem flagou esse trace?", "quem disparou esses 200 reruns?").
- Compliance plan §13 quebrado.

### Como corrigir
Em cada handler, depois do `db.add(...)` e antes do `db.commit()`:
```python
from app.domain.services.audit_service import record_audit

record_audit(
    db, "trace.flagged",
    organization_id=trace.organization_id,
    actor_user_id=user.id,
    target_type="trace",
    target_id=trace.id,
    payload={"reason": payload.reason, "note": payload.note, "flag_id": flag.id},
)
```

Para `bulk_flag_traces`, um audit por trace **ou** um audit "trace.bulk_flagged" com `payload={"trace_ids": [...], "reason": ...}`.

Para `rerun_trace`:
```python
record_audit(
    db, "trace.rerun_requested",
    organization_id=trace.organization_id,
    actor_user_id=user.id,
    target_type="trace",
    target_id=trace.id,
    payload={"new_trace_id": new_trace.id, "model": payload.model},
)
```

### Como evitar regressão
Teste `test_flag_trace_creates_audit_log` para cada ação.

---

## 🔵 16. `GET /traces/{id}/rag` ignora `trace.redacted`

### Onde
`apps/api/app/api/routes_trace_actions.py:192-266`

### O que está errado
Endpoint retorna `answer_preview`, `citations[].chunk`, `claims[].text` direto de `metadata` / `span.output`. Não verifica `trace.redacted`. A UI (`traces/[trace]/page.tsx:89`) mostra um badge `redigido` mas o endpoint RAG **não honra** a flag.

### Impacto
Trace marcado como redigido por política de privacidade ainda vaza conteúdo via endpoint RAG. Quebra LGPD/GDPR se a flag existe por requisição explícita do usuário/owner do dado.

### Como corrigir
Em `get_trace_rag`, logo após `load_trace`:
```python
if trace.redacted:
    return {
        "retrieved_docs": 0,
        "avg_score": None,
        "grounded_claims": None,
        "ungrounded_claims": None,
        "hallucination_risk": "unknown",
        "answer_preview": None,
        "citations": [],
        "claims": [],
        "claim_to_chunk": [],
        "redacted": True,
    }
```

(Adicionar `redacted: bool = False` ao schema `RagConsolidatedOut`.)

UI mostra mensagem "Conteúdo redigido por política de privacidade." quando `response.redacted === true`.

### Como evitar regressão
Teste com `trace.redacted=True` retornando RAG vazio + `redacted=True`.

---

## 🔵 17. `list_organization_members` sem paginação

### Onde
`apps/api/app/api/routes.py` (commit `3083e31`)

### O que está errado
Join `Membership × User` sem `limit`. Org com 5k membros = response JSON gigante (alguns MB) + custo de serialização Pydantic alto + risco de DoS em endpoint autenticado.

### Como corrigir
1. Adicionar `limit: int = Query(50, ge=1, le=200)` e `cursor: str | None = Query(None)`.
2. Ordenar por `Membership.created_at`, `User.id` para cursor estável.
3. Retornar `{"data": [...], "next_cursor": ...}`.

### Como evitar regressão
Teste com 250 memberships verifica que default page traz 50 e cursor funciona.

---

## 🟡 18. `bulk_flag_traces` permite duplo-flag

### Onde
`apps/api/app/api/routes_trace_actions.py:269-288`

### O que está errado
Sem deduplicação por `(trace_id, user_id, reason)` em janela curta. Duplo-clique no botão "Flagear" cria duas linhas em `trace_flags`. Contagem de flagged inflada.

### Como corrigir
**A. Constraint de banco**:
```python
# em models.py TraceFlag:
__table_args__ = (
    UniqueConstraint("trace_id", "user_id", "reason", name="uq_trace_flag_user_reason"),
)
# migration alter
```

**B. Checagem aplicacional + 409 Conflict**:
```python
existing = (
    db.query(TraceFlag)
    .filter(
        TraceFlag.trace_id == trace.id,
        TraceFlag.user_id == user.id,
        TraceFlag.reason == payload.reason,
        TraceFlag.created_at >= utcnow() - timedelta(seconds=10),
    )
    .first()
)
if existing:
    return existing  # idempotente
```

Recomendo **B** — idempotente em janela curta sem precisar de migration.

### Como evitar regressão
Teste `test_double_flag_same_reason_returns_existing`.

---

## Checklist para PR de correção

Antes de marcar como pronto:

- [ ] Bug #1: **adiado** — spec completa em `docs/plans/evalops-async-worker-replay-spec.md`. Implementar após correção dos demais bugs (requer Fase A–E: arq + worker + rota + front + testes, ~11h).
- [x] Bug #2: `listExports` integrado em `exports/page.tsx` — lista vem do servidor, mesclada com `knownIds`. Card "Contrato atual" removido. Coluna "Tamanho" mostra `—` (sem `file_size_bytes` no model — migration futura).
- [ ] Bug #3: Bell e WorkspaceSwitcher montados em `EvoTopbar.tsx`/`Sidebar.tsx`.
- [ ] Bug #4: backend aceita `duration_gt` / `rag=true`, frontend não filtra em JS.
- [ ] Bug #5: migration `0006_prompt_ref_index.py` + LIMIT na query + `usage_count` honesto.
- [ ] Bug #6: subquery/window function para `last_score` + índice composto.
- [ ] Bug #7: cálculo de p95 corrigido.
- [ ] Bug #8: schema `min_length=1` em `NotificationMarkReadIn.ids`.
- [ ] Bug #9: action normaliza `""` → `null`.
- [ ] Bug #10: status CSV no `list_traces` + overview pede `error,partial`.
- [ ] Bug #11: pelo menos botão "voltar à página 1" ativo.
- [ ] Bug #12: `_to_utc` helper aplicado em todos os subtractions.
- [ ] Bug #13: RAG endpoint não inventa totais; UI exibe `—`.
- [ ] Bug #14: `cursor` query param no exports listing **ou** remover `next_cursor` da response.
- [ ] Bug #15: `record_audit` em flag/bulk-flag/rerun.
- [ ] Bug #16: `trace.redacted` honrado em `GET /traces/{id}/rag`.
- [ ] Bug #17: paginação em members.
- [ ] Bug #18: dedup em flag_trace.
- [ ] Teste e2e cobrindo ações reais (não só render).
- [ ] `pytest` 100% verde.
- [ ] `tsc --noEmit` limpo.
- [ ] Documentação atualizada: `docs/07-api-spec.md` para os novos params; `docs/plans/refatoração_identica.md` §14 carry-over revisado.
