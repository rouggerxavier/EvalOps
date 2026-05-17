# Plano de Execução — Fase 7 (Arquitetura e Manutenção)

Data: 2026-05-14
Branch alvo: `main`
Fonte: `docs/plans/evalops-remediation-roadmap.md` (seção "Fase 7"),
`docs/plans/baseline.md`, auditoria de código do checkout atual.
Pré-requisito: Fases 1–6 concluídas (✅ confirmado em `evalops-remediation-roadmap.md`).

> **Atualização pós-merge 7B/7C (2026-05-17)**: este plano agora é
> principalmente histórico. O estado real em `main` (`f13f24c`) mudou:
> 7A está materialmente implementada com Alembic e compose de migração, 7B está
> **parcial**, 7C está **feito** em `9e9a517`, e 7D está **parcial** porque
> `40cf27a` já implementou retry/drop reliability no SDK. Use
> `docs/audits/evalops-phase7-status-after-7bc.md` para o inventário atual e
> `docs/plans/evalops-phase7-next-steps.md` para a próxima ordem operacional.
> Não use a seção antiga de 7D como prompt de implementação sem aplicar a
> reinterpretação documentada nesses arquivos.

> **Escopo**: este documento **planeja**. Nenhuma migration, refatoração, novo
> arquivo produtivo ou commit pode ser feito a partir deste plano sem PR
> separado por subfase. O documento divide a Fase 7 em **6 subfases** menores
> (7A → 7F) para reduzir blast radius por PR e permitir bisect.

---

## 0. Resumo executivo

A Fase 7 originalmente foi descrita como "extração de services + Alembic +
structured logging + polish (G-22, G-26, G-27, G-29)". Auditando o checkout
atual descobri:

1. **Alguns "polish" já foram absorvidos por fases anteriores**:
   - `experiment_service.py` já existe (Fase 3, `apps/api/app/domain/services/experiment_service.py`, 384 linhas).
   - `audit_service.py` já existe (Fase 4, 43 linhas) — não precisa ser criado.
   - `rate_limit_service.py` já existe (Fase 2, in-memory, 91 linhas) — Fase 7
     o **distribui em Redis**, não o cria.
   - `usage_service.py`, `eval_service.py`, `redaction_service.py` já existem.
2. **Pendências reais da Fase 7**:
   - **Migrations**: `apps/api/app/main.py:17-19` ainda usa
     `Base.metadata.create_all` no `lifespan`. `ensure_schema_compatibility`
     em `db.py:66-80` aplica um único `ALTER TABLE` ad-hoc. Toda mudança de
     schema das Fases 2–6 está documentada como `ALTER TABLE` manual em
     `models.py` (G-16 audit_logs nullable; G-07 spans/tokens em
     `usage_counters`/`plans`; G-12 `monthly_judge_budget_usd`; G-21
     `traces.deleted_at`). **Sem Alembic, prod não pode receber upgrade
     seguro.**
   - **Service extraction parcial**: a maior parte da lógica de Fase 1/2/4/6
     ficou em `routes.py` (684 linhas) — ingest de traces, criação/revogação
     de API key, soft delete de trace, paginação por cursor, audit hooks.
     `routes_phase6.py` (303 linhas) tem a lógica de export. Não há
     `trace_ingest_service`, `export_service`, nem `api_key_service`.
   - **`_project_or_404` triplicado**: confirmado em
     `routes_phase5.py:48`, `routes_phase6.py:36`, e implícito via
     `ensure_org_membership` em `routes.py` quando lê project por id. 7 call
     sites distintos no checkout (`grep -n "_project_or_404" apps/api/app/api/*.py`).
   - **Structured logging ausente**: `grep -rn "logger\|structlog"
     apps/api/app/` retorna apenas o `audit_service`. Nenhum middleware
     emite request_id, nenhum log JSON é configurado. Não há
     `logging_config.py`.
   - **SDK sem retry**: `packages/sdk-python/evalops/uploader.py:73-80`
     captura `Exception` e silencia — sem retry, sem backoff, sem dead-letter.
   - **`ApiKey.expires_at` não existe** no modelo (G-26 não foi tocado).
   - **Sem polling no front**: `traces/page.tsx` é server component sem
     `revalidate`, sem `swr`, sem `setInterval` (G-29 não foi tocado).
   - **Sem cleanup jobs**: `RevokedToken.expires_at` e `ExportJob.expires_at`
     existem no schema, mas nenhum job apaga rows expiradas.
3. **Riscos compostos**: refatorar routers grandes em services + adotar
   Alembic + adicionar structured logging em um único PR é exatamente o
   tipo de mudança que o roadmap proíbe (princípio 4 — "não misturar"). A
   Fase 7 **precisa** ser quebrada.

A divisão proposta abaixo (7A–7F) preserva o espírito do roadmap, mantém
PRs revisáveis, e separa o que **bloqueia deploy em Postgres novo** do que
é polish.

---

## 1. Subfases — visão geral

| # | Subfase | Foco | Gaps cobertos | Bloqueante deploy? | Modelo sugerido |
|---|---|---|---|---|---|
| 7A | Alembic / migrations | Adotar Alembic; rev 0 = snapshot atual; revs 1..N para deltas das Fases 1–6 | G-19 | **Sim** (qualquer Postgres novo) | Opus High |
| 7B | Service extraction + ownership helper | `trace_ingest_service`, `export_service`, `api_key_service`; `deps.get_owned_project()` | (refactor — não fecha gap nominal, mas resolve "dedup de `_project_or_404`") | Não | Sonnet High |
| 7C | Structured logging + request_id | Middleware request_id; logging stdlib com JsonFormatter | G-22 | Não | Sonnet High |
| 7D | SDK retry + dead-letter | Retry 3× com jitter; dead-letter local em `~/.evalops/dead/` | G-27 | Não | Sonnet Medium |
| 7E | `ApiKey.expires_at` + polling frontend | Nova coluna `expires_at`; deps rejeita expiradas (401); `traces/page.tsx` auto-refresh | G-26, G-29 | Não | Sonnet Medium |
| 7F | Redis (rate limit distribuído) + cleanup jobs | Redis-backed rate limit; cron de cleanup de `RevokedToken` e `ExportJob` expirados | G-30 (parcial) | Não (apenas para multi-worker) | Opus Medium |

Ordem recomendada: **7A → 7B → 7C → 7D → 7E → 7F** (justificativa em §3).

---

## 2. Detalhamento por subfase

### 7A — Alembic / migrations

- **Objetivo**: substituir `Base.metadata.create_all` por migrations
  versionadas; consolidar os `ALTER TABLE` manuais documentados em
  `models.py` (G-16, G-07, G-12, G-21) em revisões reversíveis.
- **Gaps cobertos**: **G-19**.
- **Arquivos prováveis**:
  - Novo `apps/api/alembic.ini`.
  - Novo dir `apps/api/alembic/` com `env.py`, `script.py.mako`, `versions/`.
  - Edita `apps/api/app/main.py:17-19` (lifespan — remover
    `create_all` em prod; manter em test via flag).
  - Edita `apps/api/app/db.py:66-80` (`ensure_schema_compatibility`
    vira `no-op` ou é removido).
  - Edita `apps/api/pyproject.toml` (`alembic>=1.13,<2` em
    `[project.dependencies]`).
  - Edita `docker-compose.prod.yml` — entrypoint roda
    `alembic upgrade head` antes do `uvicorn`.
  - Novo `apps/api/scripts/alembic-init.md` (documenta workflow para devs).
- **Mudanças permitidas**:
  - Criar `versions/0001_baseline.py` representando o schema atual completo
    (gerado via `alembic revision --autogenerate` contra um DB recém-criado
    com `Base.metadata.create_all`, depois auditado manualmente).
  - Criar revs subsequentes só se houver delta real entre snapshot e modelo
    (não deve haver — todos os `ALTER TABLE` documentados já estão
    refletidos em `models.py`).
  - Adicionar env flag `EVALOPS_USE_ALEMBIC` (default `1` em prod, `0` em
    test/dev local) durante transição. Em test mantém `create_all` para
    não quebrar suíte (que recria DB com `rm -f evalops.db*`).
  - Documentar comando de upgrade/downgrade no README da API.
- **Mudanças proibidas**:
  - Alterar **qualquer** coluna existente nesta subfase. Apenas
    materializar o schema atual em Alembic. Novas colunas (ex: 7E
    `expires_at`) ficam para a sua própria subfase **com a sua própria
    revision**.
  - Remover `ensure_schema_compatibility` antes de auditar uso em prod —
    se algum DB de dev tem `users` sem `password_hash` ainda, downgrade
    Alembic resolve, mas a função pode virar **rev 0001 inline**.
  - Tocar models, services, routers.
  - Trocar driver de Postgres (mantém `psycopg`).
- **Risco**: **Alto**. Migration incorreta em prod pode corromper schema.
  Mitigado por: rev 0 ser snapshot (não-destrutivo); flag de toggle;
  teste smoke de `alembic upgrade head` em DB efêmero (SQLite e Postgres).
- **Dependências**: nenhuma (mas precisa ser **antes** das outras subfases
  para que 7E possa criar uma revision para `expires_at`).
- **Testes obrigatórios**:
  - Smoke unit: `alembic upgrade head` em SQLite fresco produz tabelas
    iguais a `Base.metadata.create_all` (comparar `inspect(engine).get_table_names()`
    e colunas — pode usar `alembic check` ou diff manual).
  - Smoke integ: `alembic upgrade head && alembic downgrade base` round-trip
    em SQLite.
  - Smoke integ (Postgres, opt-in via env): mesmo round-trip.
  - Regressão: rodar `test_phase8` ao `test_phase12` com
    `EVALOPS_USE_ALEMBIC=1` apontando para SQLite efêmero.
- **Comandos de validação**:
  ```bash
  cd apps/api && rm -f evalops.db* && python -m pytest tests/ -q --tb=short -p no:warnings
  cd apps/api && alembic upgrade head && alembic downgrade base
  cd apps/api && EVALOPS_USE_ALEMBIC=1 rm -f evalops.db* && python -m pytest tests/test_phase8_p0_security.py tests/test_phase12_quota_eval_storage.py -q
  ```
- **Critérios de aceite**:
  - `alembic upgrade head` em DB vazio produz schema idêntico ao
    `create_all` atual (verificado por `inspect()`).
  - `alembic downgrade base` limpa todas as tabelas.
  - Regressão Fase 1–6 verde com flag ativada.
  - `docker-compose.prod.yml` roda `alembic upgrade head` no boot.
- **Rollback**: revert do PR + `alembic downgrade base` + voltar a usar
  `create_all`. Como rev 0 é não-destrutiva, downgrade não perde dados em
  prod (apenas remove o registro `alembic_version`).
- **Pós-MVP?** Não. Bloqueante para qualquer deploy Postgres novo em prod.
- **Modelo**: **Opus High**. Migration errada é cara; análise de
  `models.py` (448 linhas) + autogeneração é a parte sensível.

---

### 7B — Service extraction + ownership helper

- **Objetivo**: routers viram thin (parse → auth → service → response).
  Resolver `_project_or_404` triplicado.
- **Gaps cobertos**: nenhum gap numerado; cumpre o requisito de
  refatoração arquitetural do roadmap.
- **Arquivos prováveis**:
  - Novo `apps/api/app/domain/services/trace_ingest_service.py` — absorve
    `routes.py:264-…` (`ingest_traces`).
  - Novo `apps/api/app/domain/services/export_service.py` — absorve
    `routes_phase6.py:99-…` (`create_export`, geração de JSONL,
    `GET /download`).
  - Novo `apps/api/app/domain/services/api_key_service.py` — absorve
    `routes.py:189-…` (`create_api_key`, `revoke_api_key`).
  - Edita `apps/api/app/deps.py` — novo `get_owned_project(project_id)`
    dependency factory que reúne `get_current_user` +
    `ensure_org_membership` + `db.get(Project)` + 404 se nulo/archived.
  - Edita `apps/api/app/api/{routes.py,routes_phase5.py,routes_phase6.py}`
    — remove duplicação de `_project_or_404`, chama serviços.
  - Não toca `routes_auth.py` (auth já está limpa).
- **Mudanças permitidas**:
  - Mover queries de routers para services preservando assinatura HTTP.
  - Substituir 3× `_project_or_404` por 1× `get_owned_project`.
  - Manter assinatura pública dos endpoints **idêntica** (status codes,
    request/response schemas, headers).
  - Mover `_encode_cursor` / `_decode_cursor` (`routes.py:34-46`) para
    `app/domain/cursor.py` se forem usados em ≥ 2 services.
- **Mudanças proibidas**:
  - Introduzir hexagonal/ports&adapters, repositories abstratos, agregados
    DDD. Service = função sobre `Session`, ponto.
  - Mudar contratos OpenAPI (qualquer rename de campo, status, query param).
  - Reescrever auth (sessões, refresh tokens, 2FA).
  - Misturar 7B com 7C (request_id) — são PRs distintos.
  - Tocar `experiment_service.py` (Fase 3) além de adicionar imports.
  - Tocar `audit_service.py` (Fase 4).
- **Risco**: **Médio**. Refactor amplo, mas suíte de testes existente
  (65/65 verde antes desta fase) cobre os contratos. Risco real está em
  bug sutil de ordem de operação (ex: `record_audit` antes de
  `db.commit()` vs depois — alterar ordem pode mudar atomicidade).
- **Dependências**: 7A (Alembic) **não** é estrita, mas é fortemente
  recomendado que 7A venha primeiro para que qualquer ajuste de schema
  durante extração já tenha caminho de migration.
- **Testes obrigatórios**:
  - Toda a suíte das Fases 1–6 verde **sem alteração de teste**
    (regressão).
  - 1 teste novo: `get_owned_project` retorna 404 para projeto archived,
    404 para org sem membership, 200 para owner — single test que cobre as
    3 chamadas antigas.
  - 1 teste novo: ingest funciona via service injetado com `db` mock-light
    (smoke unit do service, sem FastAPI).
- **Comandos de validação**:
  ```bash
  cd apps/api && rm -f evalops.db* && python -m pytest tests/ -q --tb=short -p no:warnings
  # Verificar tamanho do router após extração:
  wc -l apps/api/app/api/routes.py apps/api/app/api/routes_phase6.py
  # Verificar que _project_or_404 sumiu:
  grep -rn "_project_or_404" apps/api/app/ || echo "OK: helper consolidado"
  ```
- **Critérios de aceite**:
  - `routes.py` perde pelo menos 200 linhas (ingest + api key + cursor
    helpers movidos).
  - `routes_phase6.py` perde pelo menos 80 linhas (export movido).
  - `_project_or_404` não existe mais — substituído por
    `Depends(get_owned_project)`.
  - Suíte Fase 1–6 verde sem mudança.
- **Rollback**: cada service em **commit separado dentro do PR** →
  revert granular. Sem mudança de schema, rollback é trivial.
- **Pós-MVP?** Pode ficar pós-MVP **se** o time aceitar manter routers
  gordos por mais 1–2 meses. Não bloqueia deploy. Mas o ROI de revisão
  futura cai rápido com routers de 700 linhas.
- **Modelo**: **Sonnet High**. Refactor mecânico guiado por suíte verde.
  Opus desnecessário se a suíte estiver estável após 7A.

---

### 7C — Structured logging + request_id

- **Objetivo**: logs JSON com `request_id`, `user_id`, `org_id`, `latency_ms`,
  `status_code`, `route`. Correlação de logs entre serviços em prod.
- **Gaps cobertos**: **G-22**.
- **Arquivos prováveis**:
  - Novo `apps/api/app/logging_config.py` — `configure_logging()` instala
    `logging.StreamHandler` com `JsonFormatter` custom (sem dep externa;
    pode adicionar `python-json-logger>=2.0,<4` opcionalmente para evitar
    código boilerplate — decidir no PR).
  - Edita `apps/api/app/main.py`:
    - Novo middleware `request_context` que:
      - Lê `X-Request-ID` se presente; senão gera `req_<hex8>`.
      - Armazena em `contextvars.ContextVar`.
      - Loga `request.start` e `request.end` com `latency_ms`.
      - Adiciona header `X-Request-ID` na resposta.
    - Chama `configure_logging()` no startup.
  - Edita `apps/api/app/deps.py` — após resolver user/org, escreve no
    context var para logs subsequentes terem `user_id`/`org_id`.
  - Não toca services individuais — eles só usam `logger =
    logging.getLogger(__name__)` que já é o padrão Python.
- **Mudanças permitidas**:
  - Adicionar `request_id` no payload `auth.failed_login` (G-16) — útil para
    correlacionar com logs de ingest legítimos.
  - Configurar `LOG_LEVEL` via env (já existe no `docker-compose.prod.yml`).
  - Silenciar `uvicorn.access` (substituído pelo nosso middleware) para
    evitar log duplicado.
- **Mudanças proibidas**:
  - Adotar OpenTelemetry, métricas Prometheus, traços distribuídos. Fora.
  - Logar payloads de request/response em INFO (PII risk — só DEBUG, e
    desligado por default).
  - Mudar formato de `AuditLog` (G-06).
  - Misturar com 7B.
- **Risco**: **Baixo**. Logging mal configurado pode encher disco em prod —
  mitigado por `LOG_LEVEL=INFO` default e nada de payload em log.
- **Dependências**: 7B é recomendado mas não estrito — middleware funciona
  sobre routers fat ou thin. Vai **depois** de 7B para evitar conflito de
  edição no `main.py` e `deps.py`.
- **Testes obrigatórios**:
  - Integ: `GET /health/liveness` produz exatamente 2 linhas JSON
    (`request.start`, `request.end`) com `request_id` igual em ambas.
  - Integ: `GET /health/liveness` com `X-Request-ID: rid_test` reusa esse
    id; resposta carrega `X-Request-ID: rid_test`.
  - Unit: `JsonFormatter` produz JSON válido com campos esperados.
  - Integ: rota autenticada loga `user_id`, `org_id`.
- **Comandos de validação**:
  ```bash
  cd apps/api && rm -f evalops.db* && python -m pytest tests/ -q --tb=short -p no:warnings
  cd apps/api && python -c "import json, subprocess; \
    out = subprocess.check_output(['python','-c','import logging; from app.logging_config import configure_logging; configure_logging(); logging.getLogger(\"x\").info(\"hi\", extra={\"foo\":\"bar\"})'], stderr=subprocess.STDOUT); \
    [json.loads(line) for line in out.decode().splitlines() if line.strip()]"
  ```
- **Critérios de aceite**:
  - Stdout em prod é JSON parseável linha-a-linha.
  - Toda request 2xx/4xx/5xx tem 1 par `request.start`/`request.end`.
  - `X-Request-ID` ecoado na resposta.
  - Suíte verde.
- **Rollback**: revert; logs voltam para o default do uvicorn.
- **Pós-MVP?** Pode ficar pós-MVP se ainda não há cliente externo.
  Bloqueante para suportar incident response em prod multi-cliente.
- **Modelo**: **Sonnet High**. Mecânico, mas detalhe de middleware
  ASGI exige cuidado (não pode quebrar streaming de download de export
  da Fase 4).

---

### 7D — SDK retry + dead-letter

- **Objetivo**: SDK Python (`packages/sdk-python`) recupera de falhas
  transitórias do API; perdas só após exaustão; nunca crash silencioso.
- **Gaps cobertos**: **G-27**.
- **Arquivos prováveis**:
  - Edita `packages/sdk-python/evalops/uploader.py` (linhas 73-80,
    método `_send`):
    - Retry 3×, backoff exponencial com jitter (ex: 0.5s, 1s, 2s base
      ± 50%).
    - Apenas para 5xx e timeouts. 4xx (`401`, `413`, `422`) não retentam.
    - Após exaustão, escreve batch em
      `~/.evalops/dead/<iso8601>_<hex4>.jsonl` (override via env
      `EVALOPS_DEAD_LETTER_DIR`).
  - Edita `packages/sdk-python/evalops/__init__.py` — expor
    `replay_dead_letter(path: Path | None = None)` para reupload manual.
  - Edita `packages/sdk-python/tests/test_sdk.py` — adicionar testes.
- **Mudanças permitidas**:
  - Adicionar `Retry-After` honoring quando API retorna 429.
  - Logar (via `logging`) cada retry e dead-letter write (mas SDK não
    força configuração de logger no consumidor).
- **Mudanças proibidas**:
  - Quebrar API pública do SDK (`init`, `trace`, `span`, `flush`).
  - Reescrever a fila `BackgroundUploader` para asyncio.
  - Adicionar dep nova além de `httpx` (já presente).
  - Persistir dead-letter em DB ou em remote bucket.
- **Risco**: **Baixo**. Mudança isolada no SDK; consumidores não veem
  diferença além de mais robustez.
- **Dependências**: nenhuma. Pode ir em paralelo a 7B/7C em PRs
  distintos. Lógica de retry **não toca** o backend.
- **Testes obrigatórios** (todos em `packages/sdk-python/tests/`):
  - Mock `httpx.Client.post` → `503` 3× → `200` → asserta 4 chamadas,
    nenhum dead-letter.
  - Mock 503 × 4 → asserta 4 chamadas, 1 arquivo em dead-letter dir.
  - Mock 422 → 1 chamada, **não** retenta, **não** dead-letter (erro do
    cliente, perdê-lo é correto pra não amplificar bug local).
  - Mock 429 com `Retry-After: 1` → respeita header.
  - `replay_dead_letter(tmp_path)` lê arquivo e re-submete.
- **Comandos de validação**:
  ```bash
  cd packages/sdk-python && python -m pytest tests/ -q --tb=short
  ```
- **Critérios de aceite**:
  - 5 testes acima verdes.
  - SDK não regressed: `from evalops import tracer; tracer.init(...)` continua
    funcionando como antes.
- **Rollback**: revert do PR; SDK volta a silenciar exceções.
- **Pós-MVP?** **Sim**. Pode ficar pós-MVP — afeta clientes do SDK, não
  prod do backend. Se MVP ainda for "use a UI dashboard", essa subfase é
  baixa prioridade.
- **Modelo**: **Sonnet Medium**. Mecânico, escopo restrito a um arquivo.

---

### 7E — `ApiKey.expires_at` + polling frontend

- **Objetivo**:
  - Backend: API keys ganham vencimento opcional; auth rejeita expiradas.
  - Frontend: lista de traces atualiza-se sem F5 manual (polling leve).
- **Gaps cobertos**: **G-26** (backend), **G-29** (frontend).
- **Arquivos prováveis**:
  - **G-26 backend**:
    - Edita `apps/api/app/models.py:ApiKey` — nova coluna
      `expires_at: datetime | None`.
    - Nova revision Alembic em `apps/api/alembic/versions/` (depende de 7A).
    - Edita `apps/api/app/api/routes.py:create_api_key` — aceita campo
      opcional `expires_at` em `ApiKeyCreate` (validar > now).
    - Edita `apps/api/app/deps.py:get_project_from_api_key` — após
      `selected = candidate`, verifica
      `selected.expires_at is None or selected.expires_at > utcnow()` —
      caso contrário 401 com `detail="api_key_expired"`.
    - Edita `apps/api/app/schemas.py` — adicionar campo em
      `ApiKeyOut` e `ApiKeyCreate`.
  - **G-29 frontend**:
    - Edita `apps/web/app/o/[org]/p/[project]/traces/page.tsx` —
      converter componente atual para um `TracesShell` (server, busca
      inicial) + `TracesList` (client com `useEffect`/`setInterval`).
    - **Decisão**: usar `router.refresh()` a cada 15s **apenas quando
      `document.visibilityState === "visible"`**, com botão pause.
      Alternativa simples; sem SWR/react-query (evita nova dep).
    - Edita `apps/web/lib/api.ts` — `getTraces` aceita header
      `Cache-Control: no-store` (já é server-side fetch — apenas
      garante).
- **Mudanças permitidas**:
  - Adicionar coluna `expires_at` via migration reversível.
  - Mostrar `expires_at` na UI de keys (`keys/page.tsx`) com badge
    "expira em N dias".
  - Adicionar `pause/resume` button no traces page (UX feedback do
    polling).
- **Mudanças proibidas**:
  - Rotacionar chave automaticamente quando próxima do expiry. Fora.
  - Polling em outras páginas (datasets, exports, experiments) — só
    `traces` por ora.
  - Trocar Next data fetching para client-side primário.
  - Tocar audit/redaction.
- **Risco**: **Médio**. Coluna nullable mantém compat. Polling pode
  multiplicar leitura por N × clientes — manter intervalo ≥ 15s e
  desligar em background tab.
- **Dependências**: 7A (Alembic) para a migration de `expires_at`. 7B
  e 7C não são pré-requisito mas tornam o diff backend menor (router já
  thin).
- **Testes obrigatórios**:
  - Integ backend: criar key com `expires_at = utcnow() - 1m`, usar →
    401 `api_key_expired`. Sem `expires_at` → 200.
  - Integ backend: criar key com `expires_at` no passado via POST → 422.
  - Integ backend: `expires_at` future ainda válida.
  - Frontend (Node/jsdom unit ou Playwright se disponível):
    `TracesList` chama `router.refresh()` a cada tick quando visible;
    não chama quando hidden.
  - Snapshot UI: badge "expira em N dias" renderiza.
- **Comandos de validação**:
  ```bash
  cd apps/api && rm -f evalops.db* && python -m pytest tests/ -q --tb=short -p no:warnings
  # Frontend (se Node disponível):
  cd apps/web && npx tsc --noEmit && npm test
  ```
- **Critérios de aceite**:
  - Migration aplica e reverte.
  - Key expirada → 401.
  - Polling ativo sem aumentar erros 401/429 em logs.
- **Rollback**: migration `downgrade -1` remove coluna; revert do PR
  volta UI a estática. Sem perda (coluna nullable).
- **Pós-MVP?**
  - G-26 pode ficar pós-MVP (P3 na auditoria).
  - G-29 polish puro — definitivamente pós-MVP.
- **Modelo**: **Sonnet Medium**. Backend mecânico; frontend é 1 componente.

---

### 7F — Redis (rate limit distribuído) + cleanup jobs

- **Objetivo**:
  - Substituir `rate_limit_service` in-memory por Redis sliding window
    (multi-worker safe).
  - Cleanup jobs para `RevokedToken.expires_at < now` e
    `ExportJob.expires_at < now` (purga arquivos JSONL e rows).
- **Gaps cobertos**: cumpre o "o que fica para depois" da Fase 2
  (multi-worker rate limit) e da Fase 4 (cleanup automático de exports).
  Tangencialmente toca G-30 ("polish operacional") parcialmente.
- **Arquivos prováveis**:
  - Edita `apps/api/app/domain/services/rate_limit_service.py` — adicionar
    backend Redis selecionado por env `EVALOPS_RATE_LIMIT_BACKEND`
    (`memory` default | `redis`). Manter a versão in-memory como fallback
    para test/dev.
  - Edita `apps/api/pyproject.toml` — `redis>=5,<6` opcional via extra
    `[redis]`.
  - Novo `apps/api/scripts/cleanup.py` — script CLI standalone:
    `python -m app.scripts.cleanup --revoked-tokens --exports`.
  - Edita `docker-compose.prod.yml`:
    - Novo serviço `redis:7-alpine` com healthcheck.
    - Env `REDIS_URL` no service `api`.
    - Decidir scheduler do cleanup (cron sidecar OU `apscheduler` embed
      OU recommendar k8s CronJob; **escolha recomendada**: script + cron
      do host, sem nova dep Python).
- **Mudanças permitidas**:
  - Sliding-window via `ZADD`/`ZREMRANGEBYSCORE` Redis (atômico via Lua
    se necessário) OU via fixed-window com `INCR`+`EXPIRE` (mais simples,
    aceitável para MVP).
  - Cleanup idempotente: deletar rows + `os.unlink` de `file_path` com
    try/except `FileNotFoundError`.
  - Audit log para `cleanup.exports_purged` com contagem.
- **Mudanças proibidas**:
  - Substituir rate limit in-memory por Redis em test/dev (mantém
    fallback). Tests não devem precisar de Redis.
  - Mover sessões JWT para Redis (refresh tokens fora de escopo).
  - Adotar Celery/Dramatiq/RQ.
  - Mexer em `usage_service`, `eval_service`.
- **Risco**: **Médio-alto**. Redis downtime degrada API se mal
  configurado. Cleanup pode apagar export legítimo se window de TTL
  for mal calibrada — `expires_at` é setado por quem cria o export
  (Fase 6), só apagar quando `expires_at < now - 1h` (buffer).
- **Dependências**: 7C (logging) recomendado para diagnóstico; 7A
  irrelevante. Pode ir por último.
- **Testes obrigatórios**:
  - Integ rate_limit_service backend memory: regressão Fase 2 verde.
  - Integ rate_limit_service backend redis: `fakeredis` ou skip se Redis
    indisponível.
  - Integ cleanup: criar `RevokedToken(expires_at = now - 1d)`, rodar
    cleanup → row some.
  - Integ cleanup: criar `ExportJob(expires_at = now - 2d, file_path = tmp)`
    → row some + arquivo some.
  - Integ cleanup: export ainda válido **não** é tocado.
- **Comandos de validação**:
  ```bash
  cd apps/api && rm -f evalops.db* && python -m pytest tests/ -q -k "rate_limit or cleanup" --tb=short -p no:warnings
  # Smoke Redis (se disponível):
  EVALOPS_RATE_LIMIT_BACKEND=redis REDIS_URL=redis://localhost:6379/0 python -m app.scripts.cleanup --dry-run
  ```
- **Critérios de aceite**:
  - 2 workers compartilham bucket em Redis (teste manual: 2 processos
    `uvicorn` + 1 chave → 61 reqs combinadas → 429).
  - Cleanup remove rows expiradas sem afetar válidas.
  - Default em SQLite+memory continua funcionando para dev.
- **Rollback**: env `EVALOPS_RATE_LIMIT_BACKEND=memory` reverte sem
  deploy. Cleanup é script standalone — basta não rodar o cron.
- **Pós-MVP?** **Sim** — explícito no roadmap. Só precisa antes de:
  (a) escalar para multi-worker; (b) acumular exports/revoked tokens
  ao ponto de inchar disco/DB.
- **Modelo**: **Opus Medium**. Concorrência (Redis Lua/atomicity) +
  decisão de cleanup safety justifica análise mais profunda.

---

## 3. Ordem ideal e justificativa

```
7A  →  7B  →  7C  →  7D  →  7E  →  7F
│      │      │      │      │      │
│      │      │      │      │      └── último; Redis/cleanup, opcional.
│      │      │      │      └────────── G-26 backend precisa de 7A para
│      │      │      │                  migration limpa; G-29 é UI polish.
│      │      │      └───────────────── SDK isolado; podia ir em paralelo a
│      │      │                         qualquer um, mas como sucesso é
│      │      │                         "regressão nula" do backend, ir após
│      │      │                         7C (request_id) ajuda a debugar
│      │      │                         retries em prod.
│      │      └──────────────────────── logging pega routers já thin (7B)
│      │                                e middleware já estável.
│      └─────────────────────────────── refactor; ganha de Alembic já em
│                                       lugar caso precise touch em schema.
└────────────────────────────────────── primeiro porque é único bloqueador
                                        de deploy em Postgres novo e porque
                                        todas as próximas subfases (7B/E)
                                        podem precisar criar migration.
```

Razões cruzadas:
- **7A primeiro** elimina o risco de "service extraction passou, mas
  schema em prod desalinhou".
- **7B antes de 7C** porque um router de 700 linhas com middleware
  novo + logger novo dá diff revisão impossível. Routers thin = diff
  limpo.
- **7C antes de 7D** para que retries do SDK em prod sejam debugáveis
  via `request_id`.
- **7E depende de 7A** (migration de `expires_at`); por isso fica
  após.
- **7F último** porque é o de maior superfície (nova infra Redis,
  novo deployment pattern) e o de menor urgência para MVP single-worker.

---

## 4. Tabela de decisão de modelo

| Subfase | Modelo | Effort | Justificativa |
|---|---|---|---|
| 7A | **Opus** | High | Migration errada em prod é cara. Auditoria de autogen contra schema atual (16+ tabelas, 4 alterations documentados) exige profundidade. |
| 7B | Sonnet | High | Refactor mecânico, suíte verde dá segurança. |
| 7C | Sonnet | High | ASGI middleware tem armadilhas (streaming, body buffering) mas suíte cobre. |
| 7D | Sonnet | Medium | Um arquivo SDK, escopo restrito. |
| 7E | Sonnet | Medium | Coluna nullable + 1 componente client. Mecânico. |
| 7F | **Opus** | Medium | Atomicidade Redis + segurança de cleanup justificam profundidade. |

**Subfases Sonnet (4/6)**: 7B, 7C, 7D, 7E.
**Subfases Opus (2/6)**: 7A, 7F.

---

## 5. Bloqueio de deploy e priorização

### Bloqueante para deploy Postgres novo
- **7A — Alembic**. Único item realmente bloqueante. Sem ele, qualquer
  Postgres em prod precisa dos `ALTER TABLE` manuais documentados em
  `models.py` aplicados na mão, e qualquer mudança futura de schema é
  irreversível sem downtime.

### Recomendado antes de tráfego externo / multi-cliente
- **7C — structured logging**. Diagnóstico de incidente sem
  `request_id` é cego.

### Polish / pode ficar pós-MVP
- **7B — service extraction**. Routers gordos são feios mas corretos.
  Adia-se sem custo se a equipe aceitar revisão mais lenta por mais N
  semanas.
- **7D — SDK retry**. Só afeta clientes do SDK Python. Se MVP é
  dashboard-only, baixa prioridade.
- **7E — `expires_at` + polling**. G-26 é P3 (auditoria); G-29 é UX
  refinement.
- **7F — Redis + cleanup**. Necessário **apenas** quando: (a) for
  escalar para multi-worker; (b) volume de `RevokedToken`/`ExportJob`
  expirados começar a doer. Para MVP single-worker rodando há ≤ 3
  meses, não dói.

### Resumo prioritário
1. **Bloqueia deploy prod novo**: 7A.
2. **Pré-tráfego externo**: 7A, 7C.
3. **Pós-MVP, ordem de preferência**: 7B (dívida que cresce com tempo)
   → 7E backend G-26 → 7D → 7F → 7E frontend G-29.

---

## 6. Riscos transversais e regras

1. **Não misturar subfases em um único PR.** Cada subfase = 1 PR (ou
   mais, se a subfase pedir commits separados — ex: 7B com um commit por
   service).
2. **Cada PR começa rodando regressão completa de Fases 1–6** (workaround
   SQLite obrigatório: `rm -f evalops.db*` antes de cada chamada
   `pytest`).
3. **Não introduzir novas deps Python sem justificativa de subfase**:
   - 7A: `alembic` — obrigatório.
   - 7C: `python-json-logger` — opcional; preferir stdlib se viável.
   - 7F: `redis` — obrigatório, mas só como **extra**.
4. **Não tocar contratos OpenAPI.** Adicionar campos é OK
   (`ApiKey.expires_at`), renomear ou remover não.
5. **Não tocar audit log existente.** Novos audit events (cleanup
   purges, key expiration deny) são adições, não mudanças.
6. **Postgres opt-in.** Tests continuam em SQLite via `rm -f
   evalops.db*`. Tudo que depende de Postgres (G-20 lock pessimista já
   em prod) **roda em CI separado** com Postgres real — não bloqueia
   PR local.
7. **Documentar limitação por subfase.** Cada PR encerra com seção "o
   que fica para depois" no description (regra 8 do roadmap).
8. **Rollback é commit revert + downgrade Alembic** quando aplicável.
   Sem `git push --force`. Sem `alembic stamp head` em prod.

---

## 7. Critérios globais de "Fase 7 concluída"

- [ ] 7A merged: `alembic upgrade head` aplicado em prod.
- [ ] 7B merged: `grep -rn "_project_or_404" apps/api/app/` retorna 0
      ocorrências; `routes.py` < 500 linhas; `routes_phase6.py` < 220
      linhas.
- [ ] 7C merged: `GET /health/liveness` produz 2 linhas JSON com
      `request_id` consistente.
- [ ] 7D merged: SDK retries 5xx 3× com jitter; dead-letter local
      funciona; testes Phase SDK verdes.
- [ ] 7E merged: `ApiKey.expires_at` testado (401 em expired);
      `traces/page.tsx` auto-refresh funcional.
- [ ] 7F merged: rate limit Redis-backed em prod multi-worker; cleanup
      cronizado.
- [ ] Suíte completa pytest Fases 1–6 ainda verde (com workaround
      SQLite enquanto suite-full lock não for resolvido em 7F).
- [ ] Nenhum gap da auditoria com status "aberto" entre G-19, G-22,
      G-26, G-27, G-29.

---

## 8. O que NÃO entra na Fase 7

Explicitamente fora (vai para fase futura ou descartado):

- **OpenTelemetry / métricas Prometheus** — pós-MVP.
- **Worker assíncrono** para evaluation/export — pós-MVP.
- **2FA, refresh token rotation** — fora.
- **S3-backed exports** — fora.
- **Repositories abstratos / hexagonal completo** — fora; estende além
  do princípio 4 do roadmap.
- **Migração para Postgres em dev/test** — fora; SQLite continua sendo
  o storage de teste.
- **Hash/tokenization de `user_ref`** — fora do MVP (registrado em Fase 4).
- **Suíte pytest completa em uma única invocação** — fica como dívida
  documentada; correção definitiva exige isolamento de DB por worker
  (xdist) ou Postgres em test — pós-MVP.
