# Baseline de Validação — EvalOps

Documento de snapshot dos comandos de validação e resultados executados em cada fase
do roadmap (`docs/plans/evalops-remediation-roadmap.md`).

> **Nota de recriação (2026-05-14)**: este arquivo foi reconstruído após perda de
> commit em PC anterior. O conteúdo aqui registra a validação da **Fase 3**
> conforme o estado atual do código no branch `main`. Snapshots das Fases 0, 1 e
> 2 — se necessários — devem ser reconstituídos a partir do histórico
> (`git log --oneline`) e dos próprios testes `test_phase8_p0_security.py` /
> `test_phase9_auth_hardening.py`, que **não estão presentes** neste checkout
> (ver "Pendências de baseline" abaixo).

---

## Workaround SQLite (obrigatório em todas as execuções backend)

> **Atualização Fix-7B.3 (2026-05-15) — workaround não é mais obrigatório.**
> `apps/api/tests/conftest.py` agora reata `app.db` (engine/`SessionLocal`/
> `DATABASE_URL`) a um SQLite temporário por execução, em diretório de OS
> único, usando `NullPool`. Sem conexões paradas em pool, `drop_all`/
> `create_all` sempre obtêm o lock exclusivo do SQLite, eliminando o
> `database is locked`. Validação: `cd apps/api && .venv/bin/python -m pytest
> tests -q --tb=short -p no:warnings` → **131 passed** em 3 execuções
> consecutivas sem `rm -f` entre elas. O bloco abaixo fica registrado apenas
> como **fallback histórico**.

A suíte completa `pytest apps/api/tests -q` apresentava falhas intermitentes
por **SQLite database is locked** quando rodada sem reset do arquivo entre
arquivos de teste. Workaround histórico (não mais necessário):

```bash
cd apps/api && rm -f evalops.db* && python -m pytest <alvos> -q --tb=short -p no:warnings
```

Antes do Fix-7B.3 era obrigatório apagar `evalops.db*` antes de cada invocação
do `pytest` e executar arquivos em grupos pequenos (≤ 8 arquivos por chamada)
para mitigar o lock. A suíte completa numa única chamada **não era confiável**.
Resolvido em Fix-7B.3 via isolamento de engine test-only no `conftest.py`.

---

## Fase 1 — P0 segurança/configuração (re-implementação 2026-05-14)

### Status
✅ **Re-implementada** (commit desta sessão). Fases 1+2 antigas estavam ausentes
no checkout; descoberta documentada na seção "Pendências de baseline" abaixo.
Fase 1 foi refeita nesta sessão; **Fase 2 continua ausente** e bloqueia Fase 4.

### Gaps fechados
- **G-02** — raw API key não vaza em URL. Fluxo agora usa cookie HttpOnly de
  uso único (`apps/web/lib/flash.ts`). `createApiKeyAction` redireciona com
  apenas `?created=1`; `keys/page.tsx` consome o flash via
  `consumeApiKeyFlash()` e o cookie é apagado na leitura.
- **G-03** — fallback bearer só em dev com `EVALOPS_DEV_MODE=1`. Implementado
  em `apps/web/lib/auth.ts` via helper `isDevMode()` de
  `apps/web/lib/config.ts`. Em prod, fallback é ignorado mesmo com env
  presente. `EVALOPS_DEV_MODE` precisa ser literalmente `"1"`.
- **G-04** — `EVALOPS_API_BASE_URL` validado em produção:
  `apps/web/lib/config.ts:getApiBaseUrl()` throws `ApiBaseUrlError` em prod
  quando ausente/vazio/localhost/127.0.0.1. Em dev, defaulta para
  `http://localhost:8000/v1` como antes. Páginas marketing (`/docs`,
  dashboard) capturam o erro e renderizam placeholder `#` para não quebrar
  build local — fail-loud real fica em `lib/api.ts`/`lib/auth.ts` que são os
  caminhos de chamada real à API.
- **G-17** — body size limit + spans cap. Middleware em `apps/api/app/main.py`
  retorna 413 quando body > `EVALOPS_MAX_BODY_BYTES` (default 8 MB). Ingest
  em `routes.py` retorna 422 com `detail.error="too_many_spans"` quando trace
  excede `EVALOPS_MAX_SPANS_PER_TRACE` (default 500). Defaults e getters em
  `apps/api/app/config.py`.

### Arquivos alterados
- `apps/api/app/config.py` (novo) — getters lazy de env.
- `apps/api/app/main.py` — middleware `body_size_limit`.
- `apps/api/app/api/routes.py` — pre-check de spans cap em `POST /v1/traces`.
- `apps/api/tests/test_phase8_p0_security.py` (novo) — 5 testes G-17.
- `apps/web/lib/config.ts` (novo) — `getApiBaseUrl`, `isDevMode`,
  `isProduction`, `ApiBaseUrlError`.
- `apps/web/lib/flash.ts` (novo) — flash cookie one-shot.
- `apps/web/lib/auth.ts` — `hasFallbackToken` gated, base URL lazy.
- `apps/web/lib/api.ts` — base URL lazy via `getApiBaseUrl()`.
- `apps/web/lib/actions.ts` — `createApiKeyAction` usa flash cookie.
- `apps/web/app/o/[org]/p/[project]/keys/page.tsx` — consome flash.
- `apps/web/app/docs/page.tsx` + `apps/web/app/o/[org]/p/[project]/page.tsx`
  — `apiRoot()` lazy com fallback `#` para não quebrar build local.
- `apps/web/tests/security.test.mjs` (novo) — 13 testes G-02/G-03/G-04
  (`node --test`).

### Como o fluxo de API key one-shot funciona
1. Usuário submete form em `/o/<org>/p/<proj>/keys`.
2. `createApiKeyAction` chama `POST /v1/projects/:id/api-keys`.
3. Sucesso: `setApiKeyFlash({ key, prefix })` grava cookie `evalops_api_key_flash`
   com `HttpOnly`, `SameSite=lax`, `Secure` (em prod), `Max-Age=60s`.
4. `redirect(path + "?created=1")` — URL **nunca** contém o segredo.
5. `keys/page.tsx` chama `consumeApiKeyFlash()` apenas se `qp.created` —
   cookie é lido e imediatamente apagado (set com `Max-Age=0`).
6. Refresh da página sem o cookie não exibe o segredo. Phishing-style URLs
   com `?key=...` não funcionam mais (page não lê `qp.key`).

### Como fallback bearer foi bloqueado em produção
- `isDevMode()` retorna `false` se `NODE_ENV === "production"` mesmo com env
  setada.
- `hasFallbackToken()` = `isDevMode() && Boolean(FALLBACK_TOKEN)`.
- `getAuthToken()` em `auth.ts` ignora `FALLBACK_TOKEN` quando `!isDevMode()`.
- Resultado: prod só aceita JWT de sessão real, nunca `EVALOPS_DASHBOARD_BEARER_TOKEN`.

### Como base URL é validada em produção
- `getApiBaseUrl()` em `config.ts`:
  - em prod, sem env ou env vazia → `ApiBaseUrlError("missing")`.
  - em prod, URL com hostname `localhost`/`127.0.0.1` → `ApiBaseUrlError("localhost")`.
  - em dev, defaulta para `http://localhost:8000/v1`.
- Chamado dentro de `api.ts`/`auth.ts` per-request → fail-loud em runtime.
- `/docs` e `/o/[org]/p/[project]/page.tsx` envolvem em try/catch → href
  vira `#` para não quebrar `next build` local sem env.
- **Trade-off documentado**: `next build` com `NODE_ENV=production` mas sem
  `EVALOPS_API_BASE_URL` continuará compilando (placeholder), mas qualquer
  chamada real à API em runtime vai falhar com mensagem clara. Para
  garantir falha de build em pipeline CI, validar env em script `prebuild`.

### Como body size limit e spans cap funcionam
- Middleware `body_size_limit` em `main.py`:
  - lê `Content-Length`; se presente e maior que `max_body_bytes()` → 413
    sem ler body.
  - se ausente ou indeterminado (chunked), buffera body e mede tamanho.
  - retorna `{"detail": "payload_too_large", "limit_bytes": <int>}` com 413.
  - **Limitação documentada**: chunked upload com `Content-Length` ausente
    é buferizado in-memory — recomenda-se cap adicional no reverse proxy
    em prod.
- Spans cap em `routes.py:ingest_traces`:
  - antes de qualquer persistência, itera `payload.traces` e levanta
    `HTTPException(422)` quando `len(trace.spans) > max_spans_per_trace()`.
  - payload de erro: `{"error": "too_many_spans", "trace_index", "client_trace_id", "spans", "limit"}`.

### Comandos executados e resultados

```bash
cd apps/api && rm -f evalops.db* && python -m pytest tests/test_phase8_p0_security.py -q --tb=short -p no:warnings
```
**Resultado**: `5 passed in 6.31s` ✅

```bash
cd apps/api && rm -f evalops.db* && python -m pytest tests/test_health.py tests/test_auth_flow.py tests/test_phase1_identity_access.py tests/test_phase2_tracing.py -q --tb=short -p no:warnings
```
**Resultado**: `10 passed in 7.56s` ✅

```bash
cd apps/api && rm -f evalops.db* && python -m pytest tests/test_phase5_prompts_datasets_experiments.py -q --tb=short -p no:warnings
```
**Resultado**: `8 passed in 8.32s` ✅ (Fase 3 não regrediu).

### Frontend — validação não executada nesta sessão

`npx tsc --noEmit && npm run build && npm run test` **não executou** porque
**Node.js não está instalado nesta máquina**. As mudanças TS foram revisadas
manualmente e os testes em `apps/web/tests/security.test.mjs` cobrem a
lógica canônica via re-implementação em JS plano (documentado no header do
arquivo).

**Risco assumido**: erro de tipo TS ou falha de build poderia escapar até
o próximo PC com Node disponível. Recomendado: rodar
`npx tsc --noEmit && npm run build && npm run test` no PC que tem Node
antes de mergear / fazer deploy de qualquer ambiente real.

### Riscos remanescentes (Fase 1)

1. **Frontend não validado por compilador**: trade-off acima.
2. **`next build` local não falha** em prod-NODE_ENV sem env. Decisão
   intencional para não quebrar dev/CI sem env; chamada real à API
   continua falhando loud. Adicionar gate em CI explicitamente se quiser
   fail-build.
3. **Middleware buffera body sem Content-Length**: cap adicional no
   reverse proxy recomendado em prod.
4. **Flash cookie TTL 60s**: usuário muito lento perde o segredo. Aceitável
   pelo trade-off (one-shot). Pode ser ajustado.
5. **`/docs` e dashboard com `apiRoot()=#`** quando env inválida: silenciosamente
   renderiza links broken. Bandeira de UX, não de segurança.

---

## Fase 2 — Rate limit e hardening de auth (re-implementação 2026-05-14)

### Status
✅ **Re-implementada**. Fase 4 agora **liberada** como próxima.

### Gaps fechados
- **G-01** — rate limit por API key.
  `apps/api/app/domain/services/rate_limit_service.py:check_api_key_rate_limit`.
  Sliding window de 60s, ceiling = `ApiKey.rate_limit_per_minute` (default 60
  se nulo/zero). Aplicado em `deps.get_project_from_api_key` **após** validar
  a key e o escopo `ingest`. 429 com `Retry-After` ao exceder.
- **G-13** — rate limit em `/login`. Bucket `email|ip`, janela 300s, máximo
  5 falhas. `routes_auth.login` pre-check via `check_login_rate_limit`;
  falha registra via `record_login_failure`; sucesso limpa via
  `reset_login_failures`. 429 com `Retry-After`. Mensagem 401 continua
  genérica (`invalid_credentials`) para não vazar existência de email.
- **G-15** — logout server-side. Novo modelo `RevokedToken(jti pk, expires_at,
  revoked_at)`. JWTs novos carregam `jti` (`security.create_access_token`).
  `POST /v1/auth/logout` insere `jti` na denylist. `deps.get_current_user`
  rejeita tokens com `jti` revogado (401). Logout idempotente; sem token →
  204 no-op; token malformado → 204 no-op.
- **G-16** — audit `auth.failed_login`. Cada 401 em `/login` cria um
  `AuditLog(action="auth.failed_login", organization_id=NULL,
  payload={email, ip, reason})`. Schema: `AuditLog.organization_id` virou
  **nullable** — prod DBs criados antes disso precisam de
  `ALTER TABLE audit_logs ALTER COLUMN organization_id DROP NOT NULL;`
  manual até Fase 7 (Alembic).

### Como o rate limit por API key funciona
1. Request com `X-EvalOps-Key`.
2. `get_project_from_api_key` valida hash → confirma scope `ingest`.
3. `check_api_key_rate_limit(key.id, key.rate_limit_per_minute)`:
   - lê `deque[float]` da key, descarta entradas < `now - 60s`.
   - se `len(bucket) >= limit` → retorna `retry_after = (60 - idade_mais_antiga) + 1`.
   - senão: `bucket.append(now)` → retorna `None`.
4. `None` → segue. Caso contrário → `HTTPException(429, "too_many_requests")`
   com header `Retry-After`.
5. **Limitação single-worker** (in-memory): múltiplos workers multiplicam o
   limite efetivo. Restart limpa estado. Migração para Redis na Fase 7.

### Como o rate limit de login funciona
1. `POST /v1/auth/login` extrai `email.lower().strip()` e `request.client.host`.
2. `check_login_rate_limit(email, ip)` — se `len(bucket) >= 5` em janela
   de 300s → 429 com `Retry-After`. Pre-check ANTES de verificar credenciais
   (não rola argon2 quando bloqueado, economiza CPU em ataques).
3. Credenciais inválidas: `record_login_failure(email, ip)` + audit + 401
   `invalid_credentials`. Mesma resposta para email inexistente e senha
   errada (não revela existência).
4. Credenciais válidas: `reset_login_failures(email, ip)` zera bucket →
   gera JWT → 200.

### Como o logout invalida token
1. `POST /v1/auth/logout` com `Authorization: Bearer <jwt>`.
2. Sem header / malformado / não-decodificável / sem `jti`+`exp` → 204
   sem efeito (idempotente).
3. Token decodificado com `jti`+`exp` → se não está em `RevokedToken`,
   insere row `(jti, expires_at=fromtimestamp(exp))`. Se já existir →
   no-op silencioso (idempotente).
4. Sempre 204.
5. `get_current_user` (todas as rotas autenticadas): após decode, se
   `claims.jti` está em `RevokedToken` → 401.
6. **Comportamento de tokens legados**: JWTs emitidos antes do rollout
   da Fase 2 não têm `jti` → `get_current_user` os aceita até expirar.
   Validado em `test_legacy_token_without_jti_still_works_until_exp`.

### Como o audit de failed_login foi implementado
- Helper `_audit_failed_login(db, email, ip, reason)` em `routes_auth.py`:
  cria `AuditLog(id=new_id("aud"), organization_id=None, actor_user_id=None,
  action="auth.failed_login", target_type="user", target_id=None,
  payload={"email", "ip", "reason"})` e commita.
- Acionado **dentro** do branch de falha de credencial em `login()`,
  cobrindo tanto email inexistente quanto senha errada.
- **Nunca** inclui senha ou token no `payload`.
- `organization_id` nullable porque login falho não tem contexto de org.

### Arquivos alterados
- `apps/api/app/models.py` — `AuditLog.organization_id` nullable; novo
  `RevokedToken`.
- `apps/api/app/security.py` — `create_access_token` agora emite `jti`.
- `apps/api/app/deps.py` — `get_current_user` consulta denylist;
  `get_project_from_api_key` aplica rate limit por key.
- `apps/api/app/domain/services/rate_limit_service.py` (novo).
- `apps/api/app/api/routes_auth.py` — login com rate limit + audit;
  novo `POST /v1/auth/logout`.
- `apps/api/tests/test_phase9_auth_hardening.py` (novo) — 14 testes.

### Comandos executados e resultados

```bash
cd apps/api && rm -f evalops.db* && python -m pytest tests/test_phase9_auth_hardening.py -q --tb=short -p no:warnings
```
**Resultado**: `14 passed in 15.36s` ✅

```bash
cd apps/api && rm -f evalops.db* && python -m pytest tests/test_phase8_p0_security.py -q --tb=short -p no:warnings
```
**Resultado**: `5 passed in 6.26s` ✅ (Fase 1 não regrediu)

```bash
cd apps/api && rm -f evalops.db* && python -m pytest tests/test_health.py tests/test_auth_flow.py tests/test_phase1_identity_access.py tests/test_phase2_tracing.py -q --tb=short -p no:warnings
```
**Resultado**: `10 passed in 8.04s` ✅

```bash
cd apps/api && rm -f evalops.db* && python -m pytest tests/test_phase5_prompts_datasets_experiments.py -q --tb=short -p no:warnings
```
**Resultado**: `8 passed in 9.14s` ✅ (Fase 3 não regrediu)

```bash
cd apps/api && rm -f evalops.db* && python -m pytest tests/test_phase3_analytics.py tests/test_phase6_feedback_export_usage.py tests/test_phase7_e2e_mvp_flow.py -q --tb=short -p no:warnings
```
**Resultado**: `5 passed in 6.69s` ✅

**Total**: 14 + 5 + 10 + 8 + 5 = **42 passed**.

### Frontend
Não tocado nesta fase. Não foi necessário rodar build/test frontend.

### Riscos remanescentes (Fase 2)

1. **Rate limit in-memory single-process**: múltiplos workers multiplicam
   o limite efetivo; restart zera. Migração para Redis na Fase 7.
2. **`AuditLog.organization_id` virou nullable**: prod DBs antigos precisam
   `ALTER TABLE audit_logs ALTER COLUMN organization_id DROP NOT NULL;`
   manual. Migração formal via Alembic na Fase 7.
3. **Tokens legados sem `jti`**: continuam válidos até `exp`. Comportamento
   documentado e testado. Não é vulnerabilidade — só sinal de que o
   logout só protege tokens novos.
4. **IP de cliente sem proxy-trust**: `request.client.host` retorna o peer
   direto. Atrás de proxy/CF, todos os logins chegam com o mesmo IP. Como
   o bucket é `email|ip`, ataque distribuído rotacionando email contorna
   o limit. Adicionar trust de `X-Forwarded-For` configurável fica para
   Fase 7 (não é regressão — comportamento sempre foi assim).
5. **Sem cleanup de `RevokedToken` expirados**: tabela cresce. Job de
   limpeza fica para Fase 7. Volume baixo no MVP — risco baixo.

### Fase 4 — liberada

Com Fase 1 + Fase 2 + Fase 3 verdes, **a Fase 4 (audit log universal,
redaction/PII, export download, soft delete) pode iniciar**. Ver
roadmap para escopo detalhado.

---

## Fase 3 — Experiments reais (validação 2026-05-14)

### Status
✅ **Concluída** (commits `da11b2c`, `72a9923`, `1c57ae0`).

### Evidências de implementação no código

- `apps/api/app/domain/services/experiment_service.py` (novo, 384 LOC).
  - `validate_variants()` — garante nomes únicos e `baseline_variant ∈ variants`.
  - `_resolve_prompt_version()` — aceita id, `slug@version` ou slug
    (resolve para `current_version`).
  - `_synthesize_variant_output()` — renderiza template Jinja com
    `{user_message, ...}` e anexa `[model=... params=...]` para garantir
    divergência mesmo sem `prompt_version_ref`.
  - `execute_experiment()` — para cada item × variant: resolve template →
    sintetiza output → roda rubric sobre output sintetizado → agrega métricas
    (`pass_rate`, `avg_score`, `avg_latency_ms`, `total_cost_usd`,
    `avg_cost_usd_per_item`) → compara contra baseline → checa
    `pass_criteria`. Formato de resposta (`by_variant`, `comparisons`,
    `criteria_failures`, `run_metadata`) preservado.
- `apps/api/app/api/routes_phase5.py` — agora importa
  `execute_experiment` e `validate_variants`; rota `POST /experiments/{id}/run`
  delega ao service e captura `ExperimentValidationError` como `422`.
- `apps/api/tests/test_phase5_prompts_datasets_experiments.py` — cobre
  variants divergentes, variants idênticas (delta zero) e validação de
  baseline (commit `72a9923`).
- `docs/plans/evalops-remediation-roadmap.md` — linha de status da Fase 3
  marcada como `✅ Concluída (2026-05-14)`.

### Frontend
Não houve alteração em `apps/web` na Fase 3. **Não foi necessário rodar build
frontend** (`npx tsc --noEmit && npm run build && npm run test` dispensado).

### Comando primário da Fase 3

```bash
cd apps/api && rm -f evalops.db* && python -m pytest tests/test_phase5_prompts_datasets_experiments.py -q --tb=short -p no:warnings
```

**Resultado**: `8 passed in 8.81s` ✅

### Regressão das Fases 1 e 2

> ⚠️ Os arquivos `tests/test_phase8_p0_security.py` e
> `tests/test_phase9_auth_hardening.py` referenciados no roadmap como evidência
> das Fases 1 e 2 **não estão presentes** neste checkout. Provavelmente foram
> commitados no PC anterior e ainda não chegaram a `main`. A regressão foi
> rodada com os arquivos existentes:

```bash
cd apps/api && rm -f evalops.db* && python -m pytest tests/test_health.py tests/test_auth_flow.py tests/test_phase1_identity_access.py tests/test_phase2_tracing.py -q --tb=short -p no:warnings
```

**Resultado**: `10 passed in 7.32s` ✅ (4 arquivos / 10 testes — ausência de
phase8/phase9 registrada como pendência).

### Validação adicional

```bash
cd apps/api && rm -f evalops.db* && python -m pytest tests/test_phase3_analytics.py tests/test_phase6_feedback_export_usage.py tests/test_phase7_e2e_mvp_flow.py -q --tb=short -p no:warnings
```

**Resultado**: `5 passed in 6.14s` ✅

### Resumo de execução

| Suíte | Arquivos | Testes | Resultado | Tempo |
|---|---|---|---|---|
| Fase 3 primária | 1 | 8 | ✅ pass | 8.81s |
| Regressão Fases 1 e 2 (parcial) | 4 | 10 | ✅ pass | 7.32s |
| Validação adicional (Fases 3/6/7) | 3 | 5 | ✅ pass | 6.14s |
| **Total executado** | **8** | **23** | **✅ pass** | **~22s** |

### Riscos remanescentes

1. **Phase 3 não exercita LLM real**: o output sintetizado é determinístico
   (`render + [model=... params=...]`). Comparações A/B refletem diferença de
   *config*, não de *qualidade de modelo*. Execução com LLM real fica para
   Fase 7 (worker assíncrono) — fora de escopo do MVP.
2. **`prompt_version_ref` ausente**: variants sem ref usam template-default
   `{{ user_message }}`. Continua produzindo divergência se `model` ou `params`
   diferem, mas variants com tudo idêntico produzem score idêntico (já
   coberto por teste).
3. **`pass_criteria` sem range checks**: valores absurdos (`min_pass_rate=2.0`)
   silenciosamente falham toda variant. Sem validação na criação. Follow-up
   sugerido para Fase 5 (contratos).
4. **SQLite lock em suíte completa** (ver workaround acima): a suíte
   completa em uma única invocação ainda não é confiável; rodar em grupos.
   Solução estrutural depende da Fase 6 (Postgres em prod) ou Fase 7
   (fixtures isoladas por arquivo).
5. **Sem cobertura concorrente**: dois runs simultâneos do mesmo experiment
   não foram testados. Item de risco apenas se múltiplos workers entrarem em
   produção (não é o caso do MVP single-worker).

### Pendências de baseline

- Recuperar / recriar `tests/test_phase8_p0_security.py` (Fase 1) e
  `tests/test_phase9_auth_hardening.py` (Fase 2). O roadmap aponta 5/5 e
  13/13 testes respectivamente — não foi possível validar nesta sessão.
- Considerar incluir nas próximas execuções de regressão um comando
  consolidado da Fase 1 (G-02, G-03, G-04, G-17) e Fase 2 (G-01, G-13, G-15,
  G-16) assim que os arquivos estiverem no branch.

### Pode avançar para Fase 4?

✅ **Sim, do ponto de vista da Fase 3**: implementação presente, testes verdes,
contrato de resposta preservado, sem regressão nas suítes adjacentes.

---

## Fase 4 — Audit log, privacy e exports (2026-05-14)

### Status
✅ **Concluída**.

### Gaps fechados
- **G-06** — audit log em ações sensíveis. Helper `record_audit()` em
  `apps/api/app/domain/services/audit_service.py`. Reusa tabela `AuditLog`
  existente. Auditado: `api_key.created`, `api_key.revoked`, `rubric.created`,
  `rubric_version.created`, `prompt_version.created`, `dataset.created`,
  `experiment.run`, `evaluation.run`, `trace.deleted`. Não derruba a operação
  principal se audit falhar (try/except interno). Não registra secrets/tokens.
- **G-08** — redaction opt-in. `redaction_service.should_redact(tags, header)`
  ativa quando `tags.pii=true` **ou** header `X-EvalOps-Redact` presente.
  Spans têm `messages_in`, `messages_out`, `input`, `output` setados como
  `None` antes da persistência. `Trace.redacted=True` é persistido. GET
  trace não expõe conteúdo bruto (campos já são `None` no DB). `TraceOut`
  expõe campo `redacted: bool`.
- **G-09** — endpoint de download. `GET /v1/exports/{id}/download` em
  `routes_phase6.py`. Verifica ownership, `expires_at` (→ 410), status
  `completed` (→ 409), existência do arquivo em disco (→ 404). Retorna
  `FileResponse` com `media_type=application/x-ndjson`. Filename no header
  `Content-Disposition` é `export-{id}.jsonl` sem expor path interno.
- **G-10** — path absoluto de exports. `exports_dir()` em
  `apps/api/app/config.py`. Padrão: `Path(__file__).parent.parent / "storage"
  / "exports"` (absoluto, independente de CWD). Override via
  `EVALOPS_EXPORTS_DIR`. Cria diretório se não existir. `create_export` usa
  `exports_dir()` em vez de `Path("apps/api/storage/exports")` relativo.
- **G-21** — soft delete de traces + audit. `Trace.deleted_at: datetime | None`
  adicionado ao modelo. `DELETE /v1/traces/{id}` seta `deleted_at` em vez de
  `db.delete()`, registra `trace.deleted` no audit, retorna 204. GET/list
  filtram por `deleted_at IS NULL`. DELETE repetido retorna 404. Ingest com
  mesmo `client_trace_id` de trace deletado retorna o `trace_id` existente
  (comportamento idempotente seguro).

### Nota de migração de schema (G-21)
`Trace.deleted_at` é coluna nova. Bancos de dados existentes precisam de
migração manual:
```sql
-- SQLite
ALTER TABLE traces ADD COLUMN deleted_at DATETIME;
-- PostgreSQL
ALTER TABLE traces ADD COLUMN deleted_at TIMESTAMP WITH TIME ZONE;
```
Sem a migração, queries com `Trace.deleted_at.is_(None)` falharão em SQLite
3.x (coluna inexistente). Em produção nova o `create_all` cria a coluna
automaticamente. Migração formal via Alembic na Fase 7.

### Arquivos alterados
- `apps/api/app/config.py` — adicionado `exports_dir()`.
- `apps/api/app/models.py` — `Trace.deleted_at` nullable.
- `apps/api/app/schemas.py` — `TraceOut.redacted: bool`.
- `apps/api/app/domain/services/audit_service.py` (novo).
- `apps/api/app/domain/services/redaction_service.py` (novo).
- `apps/api/app/api/routes.py` — redaction em ingest, soft delete, audit para
  api_key.created/revoked e trace.deleted, filtro `deleted_at` em list/get/analytics.
- `apps/api/app/api/routes_rubrics.py` — audit rubric.created/rubric_version.created.
- `apps/api/app/api/routes_evaluations.py` — audit evaluation.run.
- `apps/api/app/api/routes_phase5.py` — audit prompt_version.created/dataset.created/experiment.run.
- `apps/api/app/api/routes_phase6.py` — `exports_dir()`, download endpoint,
  fix de timezone naive/aware na comparação de `expires_at`.
- `apps/api/tests/test_phase10_audit_privacy_exports.py` (novo) — 18 testes.

### Comandos executados e resultados

```bash
cd apps/api && rm -f evalops.db* && .venv/Scripts/python.exe -m pytest tests/test_phase10_audit_privacy_exports.py -q --tb=short -p no:warnings
```
**Resultado**: `18 passed in 16.54s` ✅

```bash
cd apps/api && rm -f evalops.db* && .venv/Scripts/python.exe -m pytest tests/test_phase8_p0_security.py -q --tb=short -p no:warnings
```
**Resultado**: `5 passed in 6.15s` ✅

```bash
cd apps/api && rm -f evalops.db* && .venv/Scripts/python.exe -m pytest tests/test_phase9_auth_hardening.py -q --tb=short -p no:warnings
```
**Resultado**: `14 passed in 18.08s` ✅

```bash
cd apps/api && rm -f evalops.db* && .venv/Scripts/python.exe -m pytest tests/test_phase5_prompts_datasets_experiments.py -q --tb=short -p no:warnings
```
**Resultado**: `8 passed in 8.86s` ✅

```bash
cd apps/api && rm -f evalops.db* && .venv/Scripts/python.exe -m pytest tests/test_health.py tests/test_auth_flow.py tests/test_phase1_identity_access.py tests/test_phase2_tracing.py tests/test_phase3_analytics.py tests/test_phase6_feedback_export_usage.py tests/test_phase7_e2e_mvp_flow.py -q --tb=short -p no:warnings
```
**Resultado**: `15 passed in 12.27s` ✅

**Total Fase 4**: 18 novos + 42 regressão = **60 passed**.

### Riscos remanescentes (Fase 4)

1. **Migração de schema manual**: `Trace.deleted_at` exige ALTER TABLE em
   DBs existentes. Sem Alembic, esta coluna faltará em qualquer DB criado
   antes desta fase. Impacto: queries de list/analytics em DB antigo falham
   se SQLAlchemy não lidar com coluna ausente graciosamente (em SQLite, a
   coluna não existe, mas queries `IS NULL` falhariam). Solução: re-criar o
   DB ou rodar a SQL de migração acima.
2. **Timezone naive/aware em SQLite**: a comparação de `expires_at` em
   `download_export` normaliza tzinfo antes de comparar. Se houver outro
   trecho que compare datetimes com `utcnow()`, pode apresentar o mesmo
   bug. Follow-up: standardizar toda comparação de datetime.
3. **Redaction por heurística**: a redaction atual é opt-in (tag ou header).
   Dados sensíveis sem `pii=true` continuam sendo armazenados. PII automático
   por regex/heurística fica fora de escopo.
4. **Export path em Windows vs Linux**: `str(out_path)` usa separador do OS.
   Se o servidor for Linux, os paths gravados em `file_path` serão com `/`.
   No FileResponse, o path é passado a `open()` — funcionará em ambos. Se
   o DB for migrado entre OSes, `Path(job.file_path)` pode não existir. Risco
   baixo em MVP (deploy mono-OS).
5. **`deleted_at` não limpa dados**: trace deletado continua com spans, eventos
   e feedback no DB. Hard-delete ou purge físico fica para a Fase 7.
6. **Sem `GET /v1/audit-logs`**: audit logs criados mas não acessíveis via API.
   Endpoint de leitura fica para Fase 5 ou 7.

### Pode avançar para Fase 5?

✅ **Sim**: todos os critérios de aceite passaram. Fase 4 concluída com 18/18
novos testes e 42/42 de regressão verdes.

---

## Consolidação pós-Fase 4 — validação 2026-05-14

### Contexto

Esta máquina agora tem Node.js (`v24.15.0`, `npm 11.12.1`) e Python 3.14.4
instalados. A validação frontend da Fase 1 (`npx tsc --noEmit && npm run build
&& npm run test`) **não havia rodado** em máquina anterior por ausência de
Node — risco registrado como "trade-off documentado" na seção da Fase 1. Esta
sessão executa a validação consolidada pós-Fase 4 antes de habilitar a Fase 5.

Sessão **não tocou em código produtivo**; apenas executa suítes existentes e
atualiza este documento.

### Setup desta sessão

- Frontend: `cd apps/web && npm install` (instalou 46 pacotes; alerta de 2
  vulnerabilidades — 1 moderate, 1 high — não bloqueante para validação).
- Backend: `cd apps/api && python3 -m venv .venv && .venv/bin/pip install -e
  ".[dev]"` (Python 3.14.4 satisfaz `requires-python>=3.12`).

### Validação frontend (`apps/web`) — agora executada com Node

```bash
cd apps/web && npx tsc --noEmit
```
**Resultado**: ✅ sem erros (saída vazia).

```bash
cd apps/web && npm run build
```
**Resultado**: ✅ `Compiled successfully in 9.0s` + `Generating static pages
(8/8)`. Build artefato gerado para todas as rotas (`/`, `/changelog`, `/docs`,
`/login`, `/register`, `/app`, e 9 rotas dinâmicas `/o/[org]/p/[project]/*`).
Two warnings (não bloqueantes):
- `autoprefixer: end value has mixed support, consider using flex-end instead`
  em `app/globals.css:686:3` — questão cosmética de CSS.
- `[webpack.cache.PackFileCacheStrategy] Skipped not serializable cache item`
  para o aviso anterior — webpack não consegue serializar o objeto Warning
  no cache; não afeta build.

```bash
cd apps/web && npm run test
```
**Resultado**: ✅ `tests 13 / pass 13 / fail 0` em `105ms`. Cobre G-02, G-03,
G-04 conforme planejado em `apps/web/tests/security.test.mjs`.

**Conclusão frontend**: tipos OK, build OK, testes OK. O risco assumido na
Fase 1 ("erro de tipo TS ou falha de build poderia escapar até o próximo PC
com Node disponível") **foi fechado** — código frontend não tem regressão de
compilação nem de testes.

### Regressão backend pós-Fase 4

| Suíte | Arquivos | Testes | Resultado | Tempo |
|---|---|---|---|---|
| `test_phase8_p0_security.py` (Fase 1) | 1 | 5 | ✅ pass | 100.15s |
| `test_phase9_auth_hardening.py` (Fase 2) | 1 | 14 | ✅ pass | 177.41s |
| `test_phase10_audit_privacy_exports.py` (Fase 4) | 1 | 18 | ✅ pass | 265.82s |
| `test_phase5_prompts_datasets_experiments.py` (Fase 3) | 1 | 8 | ✅ pass | 136.94s |
| Regressão adicional (health + auth_flow + phase1/2/3/6/7) | 7 | 15 | ✅ pass | 195.87s |
| **Total executado** | **11** | **60** | **✅ pass** | **~876s (~14.6 min)** |

Comandos executados (idênticos aos do roadmap; workaround SQLite mantido):

```bash
cd apps/api && rm -f evalops.db* && python -m pytest tests/test_phase8_p0_security.py -q --tb=short -p no:warnings
cd apps/api && rm -f evalops.db* && python -m pytest tests/test_phase9_auth_hardening.py -q --tb=short -p no:warnings
cd apps/api && rm -f evalops.db* && python -m pytest tests/test_phase10_audit_privacy_exports.py -q --tb=short -p no:warnings
cd apps/api && rm -f evalops.db* && python -m pytest tests/test_phase5_prompts_datasets_experiments.py -q --tb=short -p no:warnings
cd apps/api && rm -f evalops.db* && python -m pytest tests/test_health.py tests/test_auth_flow.py tests/test_phase1_identity_access.py tests/test_phase2_tracing.py tests/test_phase3_analytics.py tests/test_phase6_feedback_export_usage.py tests/test_phase7_e2e_mvp_flow.py -q --tb=short -p no:warnings
```

> **Nota de tempo**: os tempos absolutos nesta sessão (100–266s por suíte) são
> bem maiores que os ~6–16s registrados nas seções anteriores. Hipótese: argon2
> com cost padrão em CPU diferente / sem cache de `cffi` / Python 3.14.4 (versão
> mais nova que a do PC original). **Não é regressão funcional**, mas o
> wall-clock de teste merece um follow-up se virar custo de CI.

### Fase 5 — liberada?

✅ **Sim, liberada**. Critérios:

1. Fase 1 (G-02/G-03/G-04/G-17): 5/5 backend + 13/13 frontend ✓.
2. Fase 2 (G-01/G-13/G-15/G-16): 14/14 ✓.
3. Fase 3 (G-05): 8/8 ✓.
4. Fase 4 (G-06/G-08/G-09/G-10/G-21): 18/18 ✓.
5. Regressão das suítes legadas: 15/15 ✓.
6. Frontend compila e empacota sem erros de tipo nem falha de build.
7. Nenhuma das suítes anteriores regrediu.

Fase 5 pode iniciar conforme o escopo definido em
`docs/plans/evalops-remediation-roadmap.md`.

### Deploy — bloqueios

🚫 **Deploy de produção continua bloqueado** pelos itens já registrados nas
seções acima — nenhum deles foi resolvido nesta sessão (apenas validação):

1. **Migração `Trace.deleted_at`** (Fase 4 — bloqueio para DBs existentes).
   Em produção nova `create_all` resolve; em produção com DB pré-Fase 4,
   `ALTER TABLE traces ADD COLUMN deleted_at ...` é obrigatório.
2. **Migração `AuditLog.organization_id NULL`** (Fase 2 — bloqueio para DBs
   existentes): `ALTER TABLE audit_logs ALTER COLUMN organization_id DROP
   NOT NULL`.
3. **Sem Alembic** (Fase 7): migrações continuam manuais.
4. **Rate limit single-worker in-memory** (Fase 2): proibido escalar para 2+
   workers até migrar para Redis. Em SLA de prod com 1 worker, aceitável; em
   horizonte de escala, é blocker.
5. **`EVALOPS_API_BASE_URL` precisa ser configurado em prod** com URL pública
   real — não-localhost, não-vazio (G-04 fail-loud só dispara em runtime, não
   em build).
6. **`EVALOPS_DEV_MODE` deve estar ausente / != `"1"`** em prod (G-03).
7. **Vulnerabilidades npm**: 1 moderate, 1 high reportadas por `npm install`.
   Não foi investigado o pacote afetado nesta sessão (escopo era validação,
   não correção). `cd apps/web && npm audit` pendente antes de deploy.
8. **`SQLite` em produção**: `pyproject.toml` traz `sqlalchemy` mas a config
   atual usa SQLite (`evalops.db`). Para prod, migrar para Postgres (G-25,
   Fase 6).
9. **CSS warning autoprefixer** (`app/globals.css:686:3`) — não bloqueante,
   mas evita ruído visual em DevTools.
10. **Wall-clock de teste alto** (100–266s/suíte vs. ~6–16s no PC original):
    não é blocker mas merece investigação se CI tiver budget de minutos
    apertado.

### Blockers operacionais remanescentes (não fechados nesta sessão)

Resumo único da fila já documentada acima:

| # | Item | Fase de origem | Resolve em |
|---|---|---|---|
| 1 | Alembic + migração `deleted_at` | Fase 4 | Fase 7 |
| 2 | Alembic + migração `audit_logs.organization_id` | Fase 2 | Fase 7 |
| 3 | Rate limit em Redis (multi-worker) | Fase 2 | Fase 7 |
| 4 | Cleanup de `RevokedToken` expirados | Fase 2 | Fase 7 |
| 5 | Trust de `X-Forwarded-For` configurável | Fase 2 | Fase 7 |
| 6 | Postgres em produção | — | Fase 6 (G-25) |
| 7 | Worker assíncrono / LLM real em experiments | Fase 3 | Fase 7 |
| 8 | `GET /v1/audit-logs` (leitura) | Fase 4 | Fase 5 ou 7 |
| 9 | PII automático por heurística | Fase 4 | fora MVP |
| 10 | Hard-delete / purge físico de trace | Fase 4 | Fase 7 |
| 11 | `npm audit` (1 moderate, 1 high) | nova nesta sessão | antes de deploy |

### Conclusão executiva

- Frontend ✅ validado pela primeira vez com Node real (tsc + build + 13
  testes).
- Backend ✅ 60/60 testes verdes pós-Fase 4, sem regressão.
- Fase 5 ✅ liberada para iniciar.
- Deploy ❌ continua bloqueado pelos itens 1–11 acima (todos pré-existentes,
  exceto `npm audit` que apareceu agora).

---

## Fase 5 — Contratos frontend↔backend e UX funcional (2026-05-14)

### Status
✅ **Concluída**.

### Gaps fechados
- **G-14** — Botões cosméticos / UX funcional.
  - `traces/page.tsx`: botão "Exportar JSONL" → `<Link>` real para `/exports`.
    Botão "Refresh" → `<Link>` real para reload da página. Checkboxes sem handler
    → `disabled data-status="planned"`. Tab "Flagged" renomeado para "Parciais"
    com filtro real (`status=partial`). Colunas `evo-table__sortable` sem sort
    real → classe removida. Botão "‹" de paginação → disabled com tooltip.
  - `experiments/page.tsx`: botão "Exportar relatório" → disabled +
    `data-status="planned"`. Botão "Novo experimento" → `<Link href="#create-experiment">`.
    `MoreHorizontal` → disabled + `data-status="planned"`. `<details>` de
    criação recebeu `id="create-experiment"`.
  - `prompts/page.tsx`: botão "Importar" → disabled + `data-status="planned"`.
    Botão "Novo prompt" → `<Link href="#prompt-create">`. Botão "Nova versão"
    no painel de detalhe → `<Link href="#prompt-version">`. `<details>` de
    criação receberam `id="prompt-create"` e `id="prompt-version"`.

- **G-18** — Paginação real.
  - Backend `GET /v1/traces`: parâmetro `cursor` adicionado; cursor encoda
    `(created_at.isoformat(), trace_id)` em base64 URL-safe. Query filtra por
    `(created_at < cursor_ca) OR (created_at = cursor_ca AND id < cursor_id)`
    (ordem DESC). Busca `limit+1` linhas → se `len > limit`, gera `next_cursor`
    com a última linha; senão `next_cursor = null`.
  - Fix de bug: parâmetro `status: str | None` da rota `list_traces` shadowava
    o módulo `fastapi.status`, causando AttributeError latente em projetos não
    encontrados. Renomeado para `trace_status` com `Query(None, alias="status")`
    — contrato HTTP `?status=` preservado.
  - Frontend `lib/api.ts`: `getTraces` aceita `cursor?: string`.
  - Frontend `traces/page.tsx`: `searchParams` aceita `cursor`. Botão "›"
    vira `<Link>` para `?cursor=<next_cursor>` quando `next_cursor` presente;
    disabled quando `null`. Texto mostra "(próxima página)" quando cursor ativo.

- **G-23** — Saneamento de mensagens de erro no frontend.
  - `lib/actions.ts`: `messageFromActionError` reescrito com whitelist.
    Erros HTTP da API (padrão `API NNN: <body>`) mapeados para mensagens
    seguras por status code. Padrões de leak detectados via regex (traceback,
    sqlalchemy, sqlite, psycopg, SQL SELECT/INSERT, path Python, API key evk_).
    Qualquer mensagem não mapeada → `"Algo deu errado. Tente novamente."`.
  - Whitelist: 400/422 → validação; 401 → sessão; 402 → plano; 403 → permissão;
    404 → não encontrado; 409 → conflito; 413 → payload; 429 → rate limit;
    500/unknown → genérico.

### Decisões de UX (G-14)

Abordagem para cada tipo de elemento sem ação real:
- **Ação existe no backend mas não na UI**: conectar com `<Link>` ou form real.
- **Funcionalidade futura no roadmap**: `disabled + data-status="planned" + title="Em breve"`.
- **Elemento puramente cosmético sem sentido no MVP**: remover ou ocultar.
- **Tab com contagem errada**: corrigir contagem a partir dos dados reais já carregados.

Nenhuma feature nova foi criada. Apenas ações existentes foram conectadas
ou elementos sem ação foram explicitamente marcados/desabilitados.

### Arquivos alterados

**Backend:**
- `apps/api/app/api/routes.py` — cursor pagination em `list_traces`, fix de
  shadow bug (`status` → `trace_status`), helpers `_encode_cursor`/`_decode_cursor`.
- `apps/api/tests/test_phase11_contracts_ux.py` (novo) — 5 testes G-18.

**Frontend:**
- `apps/web/lib/actions.ts` — `messageFromActionError` com whitelist G-23.
- `apps/web/lib/api.ts` — `getTraces` com `cursor` param.
- `apps/web/app/o/[org]/p/[project]/traces/page.tsx` — G-14 + G-18.
- `apps/web/app/o/[org]/p/[project]/experiments/page.tsx` — G-14.
- `apps/web/app/o/[org]/p/[project]/prompts/page.tsx` — G-14.
- `apps/web/tests/security.test.mjs` — 10 novos testes G-23.

### Como cursor pagination funciona

1. Cursor = `base64(f"{created_at.isoformat()}|{trace_id}")` (URL-safe, sem padding).
2. Cursor inválido → 400 `invalid_cursor`.
3. Query aplica filtro `(ca < cursor_ca) OR (ca = cursor_ca AND id < cursor_id)`
   com `ORDER BY created_at DESC, id DESC`.
4. Retorna `limit+1` → se há mais, `next_cursor` encoda o último item retornado;
   senão `null`.
5. Cliente que ignora `next_cursor` continua funcionando (primeira página sempre
   serve sem cursor).

### Como G-23 sanitiza erros

```
Erro da API: "API 500: Traceback (most recent call last):\n  File ..."
→ sanitizeApiError detecta padrão "API 500:" → GENERIC_ERROR
→ UI exibe: "Algo deu errado. Tente novamente."

Erro da API: "API 401: {"detail": "invalid_credentials"}"
→ sanitizeApiError detecta "API 401:" → SAFE_HTTP_MESSAGES[401]
→ UI exibe: "Sessão expirada ou não autorizado. Faça login novamente."
```

Stack traces, SQL, paths Python, API keys `evk_*` → todos detectados por
regex e substituídos por mensagem genérica antes de qualquer exibição.

### Comandos executados e resultados

```bash
cd apps/web && npx tsc --noEmit
```
**Resultado**: ✅ sem erros (saída vazia).

```bash
cd apps/web && npm run build
```
**Resultado**: ✅ `Compiled successfully in 1000ms`. Todas as rotas compiladas.

```bash
cd apps/web && npm run test
```
**Resultado**: `tests 23 / pass 23 / fail 0` ✅ (13 anteriores + 10 novos G-23).

```bash
cd apps/api && rm -f evalops.db* test_phase11.db* && python -m pytest tests/test_phase11_contracts_ux.py -q --tb=short -p no:warnings
```
**Resultado**: `5 passed in 26.16s` ✅

```bash
cd apps/api && rm -f evalops.db* && python -m pytest tests/test_phase8_p0_security.py -q --tb=short -p no:warnings
```
**Resultado**: `5 passed in 68s` ✅

```bash
cd apps/api && rm -f evalops.db* && python -m pytest tests/test_phase10_audit_privacy_exports.py -q --tb=short -p no:warnings
```
**Resultado**: `18 passed in 240s` ✅

```bash
cd apps/api && rm -f evalops.db* && python -m pytest tests/test_phase5_prompts_datasets_experiments.py -q --tb=short -p no:warnings
```
**Resultado**: `8 passed in 99s` ✅

```bash
cd apps/api && rm -f evalops.db* && python -m pytest tests/test_phase9_auth_hardening.py -q --tb=short -p no:warnings
```
**Resultado**: `14 passed in 185s` ✅

```bash
cd apps/api && rm -f evalops.db* && python -m pytest tests/test_health.py tests/test_auth_flow.py tests/test_phase1_identity_access.py tests/test_phase2_tracing.py tests/test_phase3_analytics.py tests/test_phase6_feedback_export_usage.py tests/test_phase7_e2e_mvp_flow.py -q --tb=short -p no:warnings
```
**Resultado**: `15 passed in 177s` ✅

**Total Fase 5**: 5 novos backend + 10 novos frontend + 65 regressão = **80 testes verdes**.

> **Nota SQLite**: rodas concorrentes em background conflitam no `evalops.db`.
> Workaround obrigatório: rodar cada arquivo individualmente com `rm -f evalops.db*`.
> Limitação pré-existente documentada desde Fase 3.

### Riscos remanescentes (Fase 5)

1. **Back-pagination não implementada**: botão "‹" desabilitado com `data-status="planned"`.
   Implementação requer cursor bidirecional ou acúmulo de histórico de cursors
   no cliente (URL ou estado). Deixado para Fase 6 ou demanda real.
2. **Cursor não é opaco para o cliente**: o base64 pode ser decodificado e
   manipulado. Não representa risco de segurança (o filtro apenas pagina dados
   do próprio projeto autenticado), mas poderia causar comportamento inesperado
   com cursors forjados — protegido pelo catch de `_decode_cursor` que retorna 400.
3. **Paginação apenas em traces**: outras listagens (datasets, prompts, rubrics,
   experiments) continuam sem cursor. Volume do MVP não justifica por enquanto.
4. **Tabs "Parciais" e "Lentos" filtram client-side**: a página carrega 50 traces
   sem filtro de status e filtra localmente para "partial" ou "duration>2000ms".
   Se houver paginação com cursor, a contagem de tabs pode estar sub-representada.
   Aceitável no MVP (50 traces/página).
5. **G-23 em page-level errors**: `messageFromActionError` cobre apenas Server
   Actions. Erros em rotas que renderizam diretamente (como `resolveProject` em
   exports page) ainda exibem `error.message` diretamente. Esses paths têm try/catch
   próprios mas não usam a whitelist — seguimento na Fase 6.

### Pode avançar para Fase 6?

✅ **Sim**: G-14, G-18, G-23 implementados e testados. Regressão de todas as
fases anteriores verde. Frontend tsc/build/test verdes.

---

## Fase 6 — Robustez de quota/evaluation/storage (2026-05-14)

### Status
✅ **Concluída**.

### Gaps fechados

- **G-07** — Quota mensal por spans/tokens.
  - `Plan.monthly_span_limit` e `Plan.monthly_token_limit` adicionados
    (defaults 50 000 spans / 5 000 000 tokens para o plano Free).
  - `UsageCounter.spans_ingested` e `UsageCounter.tokens_ingested` adicionados.
  - `enforce_quota()` em `usage_service.py` agora aceita os novos `field`s e
    devolve `detail = {"error": "quota_exceeded", "field": ..., "limit": ...}`
    em 402.
  - `POST /v1/traces` faz **pre-check atômico** dos três limites (traces,
    spans, tokens) antes de qualquer escrita: batch sobre limite é rejeitado
    integralmente sem deixar contador parcial.
  - Tokens são somados a partir de `span.tokens_in + span.tokens_out`. Spans
    sem tokens contribuem 0 (decisão segura: nunca estimamos para cima).
  - `increment_usage()` recebe novos kwargs `spans=` e `tokens=`.

- **G-11** — Duplicate evaluation retorna 409 (não 500).
  - `EvaluationRun` já tinha `UniqueConstraint("trace_id","rubric_id","rubric_version")`.
  - `routes_evaluations.trigger_evaluation` agora faz **pre-check** dessa
    tripla antes de rodar a rubric: 409 com
    `detail = {"error":"evaluation_run_duplicate","existing_run_id":<id>}`.
  - Como rede de segurança contra race, o `try/except IntegrityError` envolve
    `run_evaluation()` e devolve o mesmo 409 estruturado (com rollback).
  - Mensagens de erro nunca contêm SQL/stack/path Python (validado por teste).

- **G-12** — Judge budget por plano.
  - `Plan.monthly_judge_budget_usd` adicionado (default 20 USD).
  - `usage_service.judge_budget_for_org()` resolve plano da org → budget;
    fallback seguro para 20 USD quando: org sem subscription, plano sem
    coluna, valor `None`/`0`/inválido.
  - `eval_service._check_judge_budget()` agora consulta esse budget por
    projeto/org em vez da constante global (constante mantida só como
    fallback para callers sem contexto de org).
  - `routes_evaluations.trigger_evaluation` faz pre-check em 402 quando a
    rubric usa `llm_judge` E o budget já está esgotado:
    `detail = {"error":"judge_budget_exhausted","spent_usd":...,"budget_usd":...}`.
  - Rubrics que não usam `llm_judge` ignoram a checagem (não pagam o custo).

- **G-20** — Lock pessimista no usage counter.
  - `get_or_create_counter(..., lock=True)` aplica `with_for_update()` quando
    o dialeto é Postgres (helper `_is_postgres(db)` em `usage_service.py`).
  - SQLite ignora silenciosamente o `FOR UPDATE` — comportamento documentado.
  - `increment_usage()` agora chama com `lock=True`, então toda incremento
    pega lock pessimista em Postgres (read-modify-write serializado).
  - Em SQLite, o file-lock interno do próprio SQLite serializa writes —
    teste de concorrência multi-thread em SQLite é intencionalmente omitido
    por instabilidade de timing; teste pinning sequencial cobre o invariante.

- **G-25** — Postgres preparado para produção.
  - `apps/api/app/db.py` documenta os 3 formatos de URL aceitos (sqlite, sync
    psycopg, async-psycopg-rewritten). `is_postgres()` / `is_sqlite()`
    helpers expostos.
  - `docker-compose.prod.yml` (novo) traz Postgres 16 + healthcheck +
    `postgresql+psycopg` driver + restart policy + env contract explícito
    (`POSTGRES_PASSWORD` e `JWT_SECRET` obrigatórios via `${VAR:?}`).
  - SQLite continua o default em dev/test — nenhum teste muda DB.
  - **Validação Docker pendente**: o ambiente local desta sessão não tem
    Docker. A validação foi estrutural (yaml well-formed + alusão a Alembic
    + driver psycopg sync) via `test_g25_*`. Smoke real fica para o primeiro
    deploy de staging.

### Notas de migração de schema

Bancos existentes (Postgres ou SQLite com dados) precisam aplicar
**manualmente** as migrações abaixo até a Fase 7 (Alembic):

```sql
-- Plan: limites e budget
ALTER TABLE plans ADD COLUMN monthly_span_limit INTEGER NOT NULL DEFAULT 50000;
ALTER TABLE plans ADD COLUMN monthly_token_limit BIGINT NOT NULL DEFAULT 5000000;
ALTER TABLE plans ADD COLUMN monthly_judge_budget_usd NUMERIC(12,6) NOT NULL DEFAULT 20;

-- UsageCounter: spans/tokens contadores
ALTER TABLE usage_counters ADD COLUMN spans_ingested INTEGER NOT NULL DEFAULT 0;
ALTER TABLE usage_counters ADD COLUMN tokens_ingested BIGINT NOT NULL DEFAULT 0;
```

Em DBs novos (`Base.metadata.create_all`) as colunas vêm com os defaults
acima. **DBs já em produção precisam rodar o SQL acima antes de subir esta
versão**, senão queries vão falhar com `column does not exist`.

### Limitações documentadas

- **SQLite vs Postgres** para G-20: `SELECT ... FOR UPDATE` é silenciosamente
  ignorado por SQLite. O lock pessimista só protege Postgres. SQLite confia
  no file-lock global (single-writer semantics) — adequado para dev/test, não
  para concorrência real em produção. Migrar prod para Postgres é blocker
  separado (este gap só prepara o caminho).
- **Docker compose prod não foi validado end-to-end**: estrutura validada
  por teste; smoke real depende de máquina com Docker. Não é blocker desta
  fase, mas é blocker antes de qualquer deploy real.
- **Suite completa `pytest tests/` continua não confiável** por SQLite lock
  inter-arquivo — workaround `rm -f evalops.db*` por arquivo continua válido.

### Arquivos alterados

**Backend (modelos):**
- `apps/api/app/models.py` — Plan ganhou `monthly_span_limit`,
  `monthly_token_limit`, `monthly_judge_budget_usd`. UsageCounter ganhou
  `spans_ingested`, `tokens_ingested`.

**Backend (services):**
- `apps/api/app/domain/services/usage_service.py` — `ensure_subscription`
  popula novos campos; `get_or_create_counter(lock=)`; `enforce_quota`
  cobre novos fields e usa detail estruturado; `increment_usage` aceita
  `spans=`/`tokens=` + `lock=True`; helper `_is_postgres`; nova função
  `judge_budget_for_org`.
- `apps/api/app/domain/services/eval_service.py` — `_judge_spent_this_month`
  + `_budget_for_project` + `_check_judge_budget` consultam plan; novo helper
  `judge_budget_status` e `rubric_uses_llm_judge` para o pre-check no router.

**Backend (routes):**
- `apps/api/app/api/routes.py:ingest_traces` — pre-check atômico de
  spans/tokens; `increment_usage` com spans/tokens reais.
- `apps/api/app/api/routes_evaluations.py` — `_existing_run` helper;
  pre-check 409 antes de rodar; pre-check 402 de judge budget;
  `IntegrityError → 409` como rede de segurança; rubric_version resolvido
  uma vez no router.
- `apps/api/app/api/routes_phase6.py` — endpoint `/subscription` retorna
  novos campos do plano; endpoint `/usage` retorna `spans_ingested` e
  `tokens_ingested`.

**Backend (config / DB / docker):**
- `apps/api/app/db.py` — docstring detalhada de URLs suportados; helpers
  `is_postgres()`/`is_sqlite()` expostos.
- `docker-compose.prod.yml` (novo) — Postgres 16 + API com `psycopg` sync.

**Backend (testes):**
- `apps/api/tests/test_phase12_quota_eval_storage.py` (novo) — 15 testes
  cobrindo G-07 (4), G-11 (3), G-12 (3), G-20 (2), G-25 (3).
- `apps/api/tests/test_phase6_feedback_export_usage.py` — atualizado para
  o novo formato estruturado de `detail` em `quota_exceeded` (extensão
  intencional do contrato; old behavior `detail == "quota_exceeded"` foi
  preservado em texto: o campo `error` dentro do dict mantém o slug).

**Documentação:**
- `docs/plans/baseline.md` — esta seção.
- `docs/plans/evalops-remediation-roadmap.md` — Fase 6 marcada concluída.

### Como spans/tokens funcionam (G-07)

Pre-check em `POST /v1/traces`:

```
batch_traces  = len(payload.traces)
batch_spans   = sum(len(t.spans) for t in payload.traces)
batch_tokens  = sum((sp.tokens_in or 0) + (sp.tokens_out or 0)
                    for t in payload.traces for sp in t.spans)

enforce_quota(traces_ingested, batch_traces)    # 402 se exceder
enforce_quota(spans_ingested,  batch_spans)     # 402 se exceder
enforce_quota(tokens_ingested, batch_tokens)    # 402 se exceder
```

Se qualquer check 402, a função retorna **antes** de qualquer `db.add` —
contador permanece intacto. Após o ingest bem-sucedido, `increment_usage`
incrementa todos os contadores em uma única transação.

### Como duplicate eval vira 409 (G-11)

```
POST /v1/evaluations/run {trace_id, rubric_id, rubric_version?}

→ resolve rubric_version (422 se inexistente)
→ pre-check: SELECT EvaluationRun WHERE (trace,rubric,version) match
   → encontrou: 409 com {"error":"evaluation_run_duplicate","existing_run_id":<id>}
   → não encontrou: enforce_quota → run_evaluation
                    → IntegrityError? 409 com mesmo detail (race fallback)
```

Cliente recebe 409 estruturado; pode chamar `GET /v1/evaluations/{existing_run_id}`
sem reprocessar.

### Como judge budget por plano funciona (G-12)

`judge_budget_for_org(db, org_id) → float`:
1. Busca `Subscription` da org → `Plan` → `monthly_judge_budget_usd`.
2. Se org/plano/coluna ausentes ou valor `<= 0`/inválido → fallback `20.0`.

Em `trigger_evaluation`:
- Se a `RubricVersion` tem ao menos um evaluator `llm_judge` enabled:
  - Soma `EvaluationRun.cost_usd` do mês atual para o projeto.
  - Compara com `judge_budget_for_org(...)`.
  - Excedido → 402 com `{spent_usd, budget_usd}`.
- Senão: pula o check (rubrics determinísticas não pagam o custo).

`eval_service._check_judge_budget()` continua sendo a salvaguarda interna
para evaluators individuais durante a execução (caso `llm_judge` consuma o
budget mid-run).

### Como o lock pessimista foi implementado (G-20)

`get_or_create_counter(db, org_id, period, lock=True)`:
- `query = db.query(UsageCounter).filter(...)`
- `if lock and _is_postgres(db): query = query.with_for_update()`
- `row = query.one_or_none()`

`increment_usage` chama com `lock=True` → em Postgres a row é bloqueada até
o `commit()`/`rollback()`, serializando incrementos concorrentes. Em SQLite
o `with_for_update` é compilado para nada (silently ignored) — confiamos no
file-lock global do SQLite.

### Como Postgres foi preparado sem quebrar SQLite (G-25)

`db.py`:
- `DATABASE_URL` env var, default `sqlite:///./evalops.db`.
- `_normalize_database_url` reescreve `sqlite:///./...` → absoluto e
  `postgresql+asyncpg://` → `postgresql+psycopg://`.
- `connect_args = {"check_same_thread": False}` só para SQLite.
- Helpers `is_postgres()`/`is_sqlite()` para código que precise ramificar.

`docker-compose.prod.yml`:
- Postgres 16-alpine com volume nomeado `pgdata` e healthcheck `pg_isready`.
- API service com `pip install psycopg[binary]` no startup (bootstrap
  driver — Phase 7 deve mover isso para imagem custom).
- `JWT_SECRET` e `POSTGRES_PASSWORD` obrigatórios via `${VAR:?...}`.
- Sem service web (Next.js deploya separado em prod).

Nenhum teste mudou de DB — todos rodam SQLite local como antes.

### Comandos executados e resultados

```bash
cd apps/api && rm -f evalops.db* && python -m pytest tests/test_phase12_quota_eval_storage.py -q --tb=short -p no:warnings
```
**Resultado**: `15 passed in 204.93s` ✅

```bash
cd apps/api && rm -f evalops.db* && python -m pytest tests/test_phase8_p0_security.py -q --tb=short -p no:warnings
```
**Resultado**: `5 passed in 68.64s` ✅

```bash
cd apps/api && rm -f evalops.db* && python -m pytest tests/test_phase9_auth_hardening.py -q --tb=short -p no:warnings
```
**Resultado**: `14 passed in 184.21s` ✅

```bash
cd apps/api && rm -f evalops.db* && python -m pytest tests/test_phase5_prompts_datasets_experiments.py -q --tb=short -p no:warnings
```
**Resultado**: `8 passed in 113.50s` ✅

```bash
cd apps/api && rm -f evalops.db* && python -m pytest tests/test_phase10_audit_privacy_exports.py -q --tb=short -p no:warnings
```
**Resultado**: `18 passed in 241.73s` ✅

```bash
cd apps/api && rm -f evalops.db* && python -m pytest tests/test_phase11_contracts_ux.py -q --tb=short -p no:warnings
```
**Resultado**: `5 passed in 28.81s` ✅

```bash
cd apps/api && rm -f evalops.db* && python -m pytest tests/test_health.py tests/test_auth_flow.py tests/test_phase1_identity_access.py tests/test_phase2_tracing.py tests/test_phase3_analytics.py tests/test_phase6_feedback_export_usage.py tests/test_phase7_e2e_mvp_flow.py -q --tb=short -p no:warnings
```
**Resultado**: `15 passed in 155.65s` ✅

```bash
cd apps/web && npx tsc --noEmit
```
**Resultado**: ✅ sem erros (nenhum arquivo frontend tocado nesta fase).

**Total Fase 6**: 15 novos backend + 65 regressão = **80 testes verdes**.

### O que não foi feito de propósito

- **Alembic**: continua na Fase 7 — migrações ficam manuais (SQL acima).
- **Worker assíncrono / Celery / RQ**: judge budget exhausted devolve 402
  síncrono; sem fila para retry.
- **Stripe / billing real**: plan limits mudados via SQL/admin; sem upgrade
  flow.
- **Redis para rate limit / locks distribuídos**: continua na Fase 7.
- **OpenTelemetry**: nada foi instrumentado — Fase 7.
- **Refatoração arquitetural**: services existentes foram estendidos, não
  reescritos. Routes continuam finas.
- **Frontend**: nenhum arquivo tocado. UI ainda não exibe `monthly_span_limit`/
  `monthly_token_limit`/`monthly_judge_budget_usd` mesmo que a API agora
  retorne — entrega para próxima onda de UX.

### Riscos remanescentes

1. **Lock pessimista em SQLite é no-op**: concorrência real em SQLite ainda
   pode perder updates sob carga (raro com single-worker MVP). Mitigação:
   migrar prod para Postgres usando `docker-compose.prod.yml`.
2. **Budget gating não rateia spending parcial**: se um run consume USD
   $0.30 e o budget restante era $0.20, o overshoot de $0.10 é aceito (já
   estava em flight). Pre-check usa "spent < budget" antes de iniciar; o
   spend real só é contabilizado depois. Mitigação: futuro hard-cap no
   evaluator individual (já existe `_check_judge_budget` per-evaluator).
3. **Token estimation = 0 para spans sem tokens declarados**: se a SDK
   esquece de enviar `tokens_in`/`tokens_out`, esses spans não consomem
   quota de tokens. Decisão consciente — não estimamos para cima para evitar
   cobrar por uso fantasma.
4. **Docker compose prod não validado em runtime**: estrutura OK, mas o
   primeiro `docker compose up` em staging pode revelar gaps de env
   (`JWT_SECRET` vem de onde, etc.). Smoke obrigatório antes de prod.
5. **Migrações manuais frágeis**: cada DB existente precisa rodar o SQL
   acima exatamente uma vez. Sem Alembic, esquecer = quebra silenciosa.
   Bloqueante para Fase 7.
6. **`psycopg[binary]` instalado em runtime**: o `pip install` no `command:`
   do compose roda a cada start. Lentidão + risco de rede. Phase 7 deve
   mover para imagem Docker pré-construída.

### Pode avançar para Fase 7?

✅ **Sim**: G-07/G-11/G-12/G-20/G-25 implementados e testados; regressão de
todas as fases anteriores (1-5) verde com 80 testes; nenhum contrato público
quebrou (extensão estruturada de `quota_exceeded` documentada).

**Bloqueios para deploy continuam**: Alembic (Fase 7), Redis (Fase 7),
OpenTelemetry (Fase 7), `npm audit` (pré-existente), validação Docker real
(esta fase). Ver tabela em "Consolidação pós-Fase 4" + adições desta fase.

---

## Fase 7A — Alembic + migrações formais (2026-05-14)

### Status
✅ **Concluída**. G-19 fechado para SQLite; Postgres pendente apenas em
validação operacional (Docker indisponível no host). Schema management
continua dual: Alembic ativado por env flag para prod, `create_all`
permanece como caminho default para a suíte de testes.

### Gaps fechados
- **G-19** — Alembic adotado. Diretório `apps/api/alembic/` com `env.py`
  + `script.py.mako` + `versions/0001_baseline_schema.py` representando
  o schema completo das Fases 1–6 (todas as tabelas, índices, uniques,
  FKs e os ALTER documentados em `models.py`: `audit_logs.organization_id`
  nullable G-16, `traces.deleted_at` G-21, `plans.monthly_span_limit`/
  `monthly_token_limit` G-07, `plans.monthly_judge_budget_usd` G-12,
  `usage_counters.spans_ingested`/`tokens_ingested` G-07, e a tabela
  `revoked_tokens` G-15).

### Mudanças
- **Novos**:
  - `apps/api/alembic.ini` — config sem URL hardcoded; lida do env.
  - `apps/api/alembic/env.py` — resolve `DATABASE_URL` /
    `EVALOPS_DB_URL` via `_normalize_database_url` do app; ativa
    `render_as_batch=True` em SQLite; sinaliza `compare_type` /
    `compare_server_default` para autogenerate fiel.
  - `apps/api/alembic/script.py.mako` — template padrão.
  - `apps/api/alembic/versions/0001_baseline_schema.py` — 26 tabelas,
    todos os índices e uniques. Reversível (`downgrade()` drop_all).
  - `docs/ops/database-migrations.md` — referência operacional (SQLite,
    Postgres, stamp em DB legado, autoria de novas revisions).
- **Editados**:
  - `apps/api/pyproject.toml` — `alembic>=1.13,<2` adicionado.
  - `apps/api/app/main.py` — lifespan respeita
    `EVALOPS_USE_ALEMBIC=1`: roda `alembic upgrade head` em prod;
    permanece em `create_all` por default para tests/dev.
  - `apps/api/app/db.py` — docstring atualizado refletindo Fase 7A.

### Configuração
- **Env flag**: `EVALOPS_USE_ALEMBIC=1` (default unset). Prod
  (`docker-compose.prod.yml`) deve setar — entrypoint pode também
  rodar `alembic upgrade head` antes do `uvicorn` (alteração do
  compose **fora do escopo de 7A** para evitar PR grande).
- **DB URL**: Alembic usa o mesmo `DATABASE_URL`/`EVALOPS_DB_URL` do
  app, normalizado pelo helper compartilhado em `app/db.py`.

### Migração para DB existente

Três caminhos documentados em `docs/ops/database-migrations.md`:

1. **DB vazio (SQLite ou Postgres novo)**: `alembic upgrade head`.
2. **DB de produção atual (Phase 1–6 já aplicado via `create_all` + ALTERs
   manuais)**: `alembic stamp 0001_baseline` — escreve `alembic_version`
   sem tocar schema. Subsequentes `alembic upgrade head` funcionam
   normalmente.
3. **Tests/CI**: deixar `EVALOPS_USE_ALEMBIC` unset; `create_all`
   continua sendo o fast path porque a fixture
   `Base.metadata.drop_all` + `create_all` é incompatível com a tabela
   `alembic_version` (seria apagada e re-migrada por cada teste).

### Validação executada

#### SQLite
```bash
cd apps/api
rm -f tmp_alembic.db
DATABASE_URL=sqlite:///./tmp_alembic.db .venv/bin/alembic upgrade head
# → Running upgrade  -> 0001_baseline, baseline schema (Phase 1-6 consolidated).
```
**Resultado**: ✅ schema criado.

```bash
rm -f tmp_create.db
DATABASE_URL=sqlite:///./tmp_create.db .venv/bin/python -c \
  "from app.db import Base, engine; from app import models; Base.metadata.create_all(bind=engine)"
# diff de tabelas + colunas + índices entre tmp_alembic.db e tmp_create.db
```
**Resultado**: ✅ `equal: True` — 26 tabelas idênticas em colunas e
índices. Listagem:

```
api_keys, audit_logs, dataset_items, datasets, evaluation_runs,
evaluation_scores, evaluators, events, experiment_runs, experiments,
export_jobs, human_feedback, memberships, organizations, plans,
projects, prompt_versions, prompts, revoked_tokens, rubric_versions,
rubrics, spans, subscriptions, traces, usage_counters, users
```

#### Round-trip
```bash
DATABASE_URL=sqlite:///./tmp_alembic.db .venv/bin/alembic downgrade base
```
**Resultado**: ✅ todas as tabelas dropadas; resta apenas
`alembic_version`.

#### Postgres
⏳ **Pendente** — Docker indisponível neste ambiente. Smoke recomendado
em staging:

```bash
DATABASE_URL=postgresql+psycopg://evalops:****@db:5432/evalops \
  alembic upgrade head && alembic downgrade -1 && alembic upgrade head
```

#### Regressão
Subconjunto de testes rodado nesta sessão com `create_all` ainda no
caminho default (flag desligada):

```bash
cd apps/api && rm -f evalops.db* && \
  .venv/bin/python -m pytest tests/test_health.py tests/test_auth_flow.py \
  tests/test_phase8_p0_security.py tests/test_phase12_quota_eval_storage.py \
  -q --tb=short -p no:warnings
```
**Resultado**: combo com 4 arquivos em uma chamada apresenta flake de
FS no WSL2 (`disk I/O error` / `attempt to write a readonly database`
em `DROP TABLE`); rodando o arquivo problemático **isolado** o
resultado é verde:

```bash
rm -f evalops.db* && \
  .venv/bin/python -m pytest tests/test_phase12_quota_eval_storage.py \
  -q --tb=line -p no:warnings
# → 15 passed in 257s
```

```bash
rm -f evalops.db* && \
  .venv/bin/python -m pytest tests/test_health.py tests/test_phase8_p0_security.py \
  -q --tb=line -p no:warnings
# → 7 passed in 90s
```

A flake de FS é pré-existente (mesma classe documentada em "Workaround
SQLite" no topo deste baseline) e não foi introduzida por 7A — a única
edição funcional em backend é a adição da branch `if _use_alembic()`
no lifespan, com `create_all` no ramo `else` (caminho default,
byte-equivalente ao pré-Fase-7A).

#### Lifespan com flag ativada
```bash
rm -f tmp_lifespan.db && \
  EVALOPS_USE_ALEMBIC=1 DATABASE_URL=sqlite:///./tmp_lifespan.db \
  python -c "from fastapi.testclient import TestClient; from app.main import app; \
             c=TestClient(app); \
             with c: print(c.get('/health/liveness').json(), c.get('/health/readiness').json())"
```
**Resultado**: ✅ lifespan roda `alembic upgrade head`, ambos health
checks 200, DB final contém `alembic_version` + 26 tabelas. Confirma
caminho prod end-to-end.

### O que não foi feito de propósito

- **Compose entrypoint** — `docker-compose.prod.yml` continua sem
  `alembic upgrade head` no boot. Mudança documentada como follow-up
  para subfase que tocar deployment (7C/7F).
- **Remoção de `create_all` / `ensure_schema_compatibility`** —
  ambos permanecem no ramo default do lifespan; remoção exige migrar
  as fixtures de teste para preservarem `alembic_version`, escopo de
  Fase 7B.
- **Postgres smoke real** — bloqueado por ambiente; documentado.
- **Autogenerate de revisões "delta"** — schema atual cabe em uma
  única revision baseline; não há delta a representar separadamente
  (todos os ALTERs documentados em `models.py` já estão consolidados
  no `0001_baseline`).
- **CI gate `alembic upgrade head`** — não foi adicionado workflow CI
  nesta sessão; comando de validação ficou registrado neste baseline e
  em `docs/ops/database-migrations.md`.

### Riscos remanescentes

1. **`create_all` ainda no caminho default**: dev/test não exercitam
   o caminho Alembic. Risco: drift entre `models.py` e
   `0001_baseline` passar despercebido. Mitigação: o procedimento de
   autoria documentado em `docs/ops/database-migrations.md` exige
   `alembic revision --autogenerate` contra um DB já no head — se há
   drift, o autogenerate detecta.
2. **Stamp em prod legado é manual**: operador precisa rodar
   `alembic stamp 0001_baseline` exatamente uma vez por DB; esquecer
   = upgrade futuro tenta recriar tabelas que existem. Mitigação: o
   runbook em `docs/ops/database-migrations.md` cobre o passo.
3. **Postgres não validado nesta sessão**: smoke obrigatório antes de
   ativar `EVALOPS_USE_ALEMBIC=1` em qualquer Postgres real.
4. **Flake de FS no WSL2 com múltiplos arquivos por chamada `pytest`**:
   já documentado em "Workaround SQLite" no topo do baseline; rodando
   isoladamente cada arquivo retorna verde. Solução estrutural (isolar
   DB por worker / migrar suite para Postgres em CI) fica para 7B+.

### Pode avançar para Fase 7B?

✅ **Sim** — bloqueador único de deploy Postgres novo (G-19) está
fechado. Próxima subfase (`7B — Service extraction + ownership
helper`) pode começar; quando ela criar nova revision (ex:
`api_keys.expires_at` em 7E), a infra Alembic já está pronta para
recebê-la com `down_revision = "0001_baseline"`.

---

## Fase 7B — Service extraction + ownership helper (2026-05-15)

### Status

✅ Concluída. Routers afinados, regras de aplicação movidas para
services, ownership/project lookup centralizado. Sem Alembic tocado
(7A já fechou), sem frontend, sem mudança de contrato público.

### Services extraídos

- **`app/domain/services/trace_ingest_service.py`** — toda a lógica de
  `POST /v1/traces` (pré-check de quota traces/spans/tokens, cap de
  spans, idempotência por `client_trace_id`, redaction, persistência de
  trace/span/event, wiring de parent/fallback, `increment_usage`).
  Função pública: `ingest_trace_batch(db, project, payload, redact_header)`.
- **`app/domain/services/export_service.py`** — dump JSONL de
  `POST /v1/exports` (filtro de traces, serialização + feedback,
  escrita de arquivo, marcação completed/error, `increment_usage`,
  audit). Função pública: `create_jsonl_export(db, project, user_id, payload)`.
- **`app/domain/services/api_key_service.py`** — list/create/revoke de
  API keys, incluindo audit. Funções: `list_keys`, `create_key`,
  `revoke_key`.
- **`experiment_service` / `usage_service`** — não foi necessário
  consolidar; já concentravam a regra desde Fases 3/6. Sem alteração.

### Ownership centralizado

Novo módulo **`app/ownership.py`** — fonte única de
project/trace/prompt/dataset/experiment/rubric/export access:

- `load_*(db, user_id, id)` — forma plain (usada quando o id vem no
  corpo do POST, ex.: `create_export`).
- `get_owned_*` — dependências FastAPI (`Depends`) para rotas onde o id
  está no path. Router faz `parse/deps/auth → service → response`.

As 6 cópias de `_project_or_404` / `_trace_or_404` / `_prompt_or_404` /
`_dataset_or_404` / `_experiment_or_404` espalhadas por
`routes_phase5.py` e `routes_phase6.py`, mais os blocos inline em
`routes.py`, `routes_rubrics.py` e `routes_evaluations.py`, agora
delegam a esse módulo. `routes_phase5.py` mantém wrappers finos com a
assinatura `(id, user_id, db)` antiga só para não reescrever 14 call
sites — a lógica vive uma única vez em `ownership.py`.

### Rotas afinadas

- `routes.py`: `ingest_traces` (≈175 linhas → 2), `list/create/revoke
  api-keys` agora chamam `api_key_service` + `get_owned_project`;
  `list_traces`, `get_trace`, `delete_trace`, `analytics_overview`
  usam `get_owned_project`/`get_owned_trace`.
- `routes_phase6.py`: `create_export` chama `export_service`;
  feedback/export usam ownership helpers; ~120 linhas de I/O saíram do
  router.
- `routes_rubrics.py` / `routes_evaluations.py`: ownership inline
  substituído por `get_owned_*` / `load_*`.

### Duplicações removidas

- 6 definições de `_*_or_404` → 1 módulo `ownership.py`.
- Bloco de persistência de trace/span/event (só existia inline).
- Lógica de filtro+serialização de export (só existia inline).
- Construção/audit de API key (só existia inline).

### Contratos preservados

Schemas Pydantic e status codes inalterados. Verificado via suíte de
contratos (`test_phase11`) e e2e (`test_phase7`) — ver abaixo.

### Testes executados (cada arquivo com DB fresca; SQLite WSL2 exige
isolamento por processo — ver "Workaround SQLite" no topo)

| Suite | Resultado |
|---|---|
| phase1 identity/access | ✅ 2 passed |
| phase2 tracing | ✅ 2 passed |
| phase3 analytics | ✅ 1 passed |
| phase4 rubrics/eval | ✅ 51 passed |
| phase5 prompts/datasets/experiments | ✅ 8 passed |
| phase6 feedback/export/usage | ✅ 3 passed |
| phase7 e2e MVP flow | ✅ 1 passed |
| phase8 p0 security (ingest) | ✅ 5 passed |
| phase10 audit/redaction/export/soft-delete | ✅ 18 passed |
| phase12 quota/eval storage | ✅ 15 passed |

`pytest tests/` completo **não** usado como critério (flake de FS no
WSL2 com múltiplos arquivos por processo, já documentado). Critério =
cada arquivo isolado verde.

### Riscos remanescentes

1. **Consistência de `deleted_at`/`archived_at`**: `get_owned_trace`
   passa a checar `trace.deleted_at` e `load_project` checa
   `archived_at` em rotas que antes **não** checavam (feedback de
   trace soft-deleted, `GET /evaluations/{id}` de trace deletado,
   `list_project_evaluations`/export download de projeto arquivado).
   Agora retornam 404 nesses casos — comportamento mais correto e
   consistente, mas é mudança observável de borda. Nenhum teste de
   regressão exercita esses caminhos; risco baixo, monitorar.
2. **Wrappers `_*_or_404` em `routes_phase5.py`**: mantidos por
   pragmatismo (evitar reescrever 14 call sites). Dívida cosmética —
   7C pode migrar para `Depends(get_owned_*)` se desejado.
3. **`routes_auth.py` não tocado**: helpers `_slugify`/`_unique_slug`
   continuam locais (lógica de registro, não ownership). Fora de escopo.

### Pode avançar para Fase 7C?

✅ **Sim** — routers críticos (`routes.py`, `routes_phase6.py`) agora
só resolvem ownership + chamam service. Regra de aplicação isolada em
`domain/services`. Modelos SQLAlchemy permanecem sem regra de negócio.
Próxima subfase (observabilidade / request_id / logging JSON, ou
`ApiKey.expires_at` em 7E) pode começar sobre base limpa.

---

## Fix-7B.1 — Soft delete consistency

Cobre achados de auditoria **A-01 (P0)**, **A-03 (P1)**, **A-04 (P1)**,
**A-05 (P1)**. Objetivo: `Trace.deleted_at` respeitado em todos os
fluxos operacionais normais. Nenhuma outra subfase implementada.

### Arquivos alterados

- `apps/api/app/domain/services/export_service.py`
- `apps/api/app/api/routes_phase5.py`
- `apps/api/app/api/routes_evaluations.py`
- `apps/api/app/domain/services/trace_ingest_service.py`
- `apps/api/tests/test_phase10_audit_privacy_exports.py` (testes)
- `apps/api/tests/test_phase5_prompts_datasets_experiments.py` (testes)
- `apps/api/tests/test_phase4_rubrics_eval.py` (testes)

### A-01 — Export respeita soft delete

`_filter_traces` agora filtra `Trace.deleted_at.is_(None)` junto com
`project_id`. Como `row_count` e a serialização de feedback/spans/eventos
derivam exclusivamente da lista retornada por `_filter_traces`, traces
soft-deletados ficam ausentes do JSONL **e** não contam para
`row_count`. Sem mudança de schema/contrato.

### A-03 — Dataset build respeita soft delete

`build_dataset_from_traces` adiciona `Trace.deleted_at.is_(None)` ao
query base. Se nenhum trace ativo sobrar, o loop não itera e o endpoint
retorna `202 {"created": 0}` — comportamento controlado, compatível com
o contrato atual.

### A-04 — Evaluations por projeto respeitam soft delete

`list_project_evaluations` adiciona `Trace.deleted_at.is_(None)` ao
join com `Trace`. Runs antigos **não** são apagados; apenas filtrados
do fluxo de listagem por projeto. Acesso direto via DB/`run_id`
permanece (linha histórica intacta).

### A-05 — Contrato de reingest de `client_trace_id` deletado

`_existing_trace_id` agora carrega o trace mesmo quando deletado. Se
`deleted_at IS NOT NULL`, levanta `HTTPException(409,
{"error":"trace_deleted","client_trace_id":"..."})`. O loop de
`ingest_trace_batch` propaga `HTTPException` (re-raise antes do
`except Exception` genérico) para o 409 chegar ao cliente em vez de ir
para a lista `errors`. Não recria trace (colidiria com
`uq_traces_project_client`) e não restaura automaticamente.
Idempotência de trace **ativo** inalterada.

### Testes adicionados

- `test_export_excludes_soft_deleted_trace` — assert trace deletado
  ausente do JSONL e `row_count == 1`.
- `test_reingest_deleted_client_trace_id_returns_409` — 409 com
  `detail.error == "trace_deleted"`, nenhuma linha nova criada.
- `test_reingest_active_client_trace_id_still_idempotent` — regressão.
- `test_build_dataset_from_traces_ignores_soft_deleted` — `created == 1`,
  item do trace deletado ausente.
- `test_list_project_evaluations_excludes_soft_deleted_trace` — run do
  trace deletado fora da listagem, row do run ainda presente no DB.

### Comandos e resultados

| Comando | Resultado |
|---|---|
| `pytest tests/test_phase10_audit_privacy_exports.py` | ✅ incl. nos 84 abaixo |
| `pytest tests/test_phase5_prompts_datasets_experiments.py` | ✅ idem |
| `pytest tests/test_phase4_rubrics_eval.py` | ✅ idem |
| `pytest tests/test_phase2_tracing.py` | ✅ idem |
| 4 arquivos-alvo juntos | ✅ 84 passed |
| Regressão focada (phase8/9/10/11/12/5) | ✅ 69 passed |
| `pytest tests` completo | ✅ 136 passed |

Fix-7B.3 já estabilizou isolamento SQLite; suíte completa roda verde
sem `rm -f evalops.db*`.

### Pode avançar para Fix-7B.2?

✅ **Sim** — A-01/A-03/A-04/A-05 fechados, suíte completa verde,
nenhum escopo proibido tocado (sem hard delete, sem endpoint admin,
sem restore, sem mudança de schema/migration, sem frontend/SDK).

---

## Fix-7B.2 — Logout real no frontend

Objetivo desta subfase: fechar o achado **A-02**, garantindo revogação
server-side (`POST /v1/auth/logout`) antes de limpar sessão local.

### Arquivos alterados

- `apps/web/lib/auth.ts`
- `apps/web/lib/auth-actions.ts`
- `apps/web/tests/security.test.mjs`
- `docs/plans/baseline.md`

### Fluxo de logout após Fix-7B.2

1. `logoutAction()` tenta obter o JWT atual da sessão via cookie HttpOnly
   (`getSessionCookieToken()`).
2. Se existir token, chama `logoutWithApi(token)`:
   `POST ${API_BASE_URL}/auth/logout` com header
   `Authorization: Bearer <token>`.
3. Independente de sucesso/erro da revogação remota, executa
   `clearSessionCookie()`.
4. Redireciona para `/`.

### Comportamento em falha de backend/rede

- Falha na chamada de logout remoto é tratada como **best effort**:
  exceção é absorvida em `logoutAction()`.
- Sessão local é sempre limpa (cookie invalidado com `maxAge: 0`).
- Não há exposição de stack, token, path interno ou detalhe sensível na UI.

### Testes web adicionados (contrato)

Arquivo: `apps/web/tests/security.test.mjs`

- `Fix-7B.2: logout calls POST /auth/logout with Authorization bearer`
- `Fix-7B.2: logout clears local session after revoke attempt`
- `Fix-7B.2: backend logout failure still clears local session`
- `Fix-7B.2: logout without token is idempotent and does not call backend`
- `Fix-7B.2: source contract has logout helper using POST + bearer`
- `Fix-7B.2: source contract tries revoke before local clear`

### Regressão backend (contrato existente)

`tests/test_phase9_auth_hardening.py` permaneceu verde, incluindo:

- invalidação de token após logout,
- persistência de `jti` em denylist,
- idempotência de logout,
- logout sem token/invalid token retornando 204.

### Comandos executados e resultados

```bash
cd apps/web && npm run test
```
✅ `29 passed`

```bash
cd apps/web && npx tsc --noEmit
```
✅ passou (observação: uma execução concorrente inicial falhou por referências
temporárias de `.next/types`; reexecução após `next build` ficou verde).

```bash
cd apps/web && npm run build
```
✅ build Next.js concluído com sucesso.

```bash
cd apps/api && .venv/bin/python -m pytest tests/test_phase9_auth_hardening.py -q --tb=short -p no:warnings
```
✅ `14 passed`

Regressão opcional executada:

```bash
cd apps/api && .venv/bin/python -m pytest tests/test_phase8_p0_security.py tests/test_phase10_audit_privacy_exports.py tests/test_phase11_contracts_ux.py tests/test_phase12_quota_eval_storage.py -q --tb=short -p no:warnings
```
✅ `46 passed`

### Pode avançar para Fix-7B.4?

✅ **Sim** — Fix-7B.2 foi implementada isoladamente; nenhuma outra subfase
Fix-7B foi executada neste trabalho.

---

## Fix-7B.4 — Quota/concurrency transaction hardening (2026-05-15)

### Status
✅ **Concluída** (A-06 + A-07).

### Resumo da mudança

- `usage_service.py` ganhou API interna atômica `apply_usage_with_quota(...)`
  para validar quota e aplicar incrementos na mesma transação.
- `get_or_create_counter(...)` foi endurecida para race de criação de
  `UsageCounter` com tratamento de `IntegrityError` e recarga da linha
  vencedora.
- Lock pessimista para linha existente foi mantido via `with_for_update()`
  quando `lock=True` e dialeto Postgres.
- Ingest deixou de fazer commit intermediário antes de usage: trace/spans/events
  + usage agora fecham no mesmo commit por item.
- Evaluation deixou de fazer commit dentro de `run_evaluation`; o commit passou
  para o router, junto de quota/usage/audit, eliminando sucesso parcial.
- Export passou a aplicar usage com a API atômica; em falha de usage o job
  permanece com `status=error` (não `completed`).

### Arquivos alterados

- `apps/api/app/domain/services/usage_service.py`
- `apps/api/app/domain/services/trace_ingest_service.py`
- `apps/api/app/domain/services/eval_service.py`
- `apps/api/app/api/routes_evaluations.py`
- `apps/api/app/domain/services/export_service.py`
- `apps/api/tests/test_phase12_quota_eval_storage.py`
- `docs/plans/baseline.md`

### Testes adicionados/ajustados (phase12)

- Quota no limite incrementa corretamente.
- Quota acima do limite retorna 402 sem incremento adicional.
- Batch rejeitado por quota não persiste `Trace`/`Span`/`Event`.
- Race de criação de `UsageCounter` recupera sem 500.
- Caminho Postgres com lock chama `with_for_update`; SQLite continua
  compatível.
- Falha simulada de usage em ingest faz rollback do trace.
- Falha simulada de usage em evaluation faz rollback do run.
- Falha simulada de usage em export marca job como `error`.
- Falha simulada de audit em export permanece fire-and-forget
  (export `completed`).

### Comandos executados e resultados

`python` não existe no PATH desta máquina; os comandos foram executados com
`.venv/bin/python`.

Além disso, o runtime desta máquina (Python 3.14) apresentou deadlock no
`fastapi.testclient.TestClient` síncrono. Foi usado **apenas em runtime**
`PYTHONPATH=/tmp/evalops_testpatch` (arquivo `sitecustomize.py` temporário em
`/tmp`) para contornar o deadlock durante os testes; **nenhum arquivo do
repositório foi alterado por esse workaround**.

```bash
cd apps/api && PYTHONPATH=/tmp/evalops_testpatch .venv/bin/python -m pytest tests/test_phase12_quota_eval_storage.py -q --tb=short -p no:warnings
```
✅ `24 passed`

```bash
cd apps/api && PYTHONPATH=/tmp/evalops_testpatch .venv/bin/python -m pytest tests/test_phase8_p0_security.py tests/test_phase10_audit_privacy_exports.py tests/test_phase4_rubrics_eval.py -q --tb=short -p no:warnings
```
✅ `78 passed`

```bash
cd apps/api && PYTHONPATH=/tmp/evalops_testpatch .venv/bin/python -m pytest tests/test_phase9_auth_hardening.py tests/test_phase11_contracts_ux.py tests/test_phase5_prompts_datasets_experiments.py -q --tb=short -p no:warnings
```
✅ `28 passed`

```bash
cd apps/api && PYTHONPATH=/tmp/evalops_testpatch .venv/bin/python -m pytest tests/test_health.py tests/test_auth_flow.py tests/test_phase1_identity_access.py tests/test_phase2_tracing.py tests/test_phase3_analytics.py tests/test_phase6_feedback_export_usage.py tests/test_phase7_e2e_mvp_flow.py -q --tb=short -p no:warnings
```
✅ `15 passed`

Opcional:

```bash
cd apps/api && PYTHONPATH=/tmp/evalops_testpatch .venv/bin/python -m pytest tests -q --tb=short -p no:warnings
```
✅ `145 passed`

### Riscos remanescentes

- **SQLite vs Postgres**: os testes de lock Postgres continuam estruturais
  (sem banco Postgres real no CI local); semântica real de lock/contenção em
  multi-worker Postgres ainda depende de smoke de integração com Postgres.
- **Audit**: permanece fire-and-forget por design (falha de audit não bloqueia
  operação principal), mantido intencionalmente.

### Pode avançar para Fix-7B.5?

✅ **Sim** — esta entrega ficou restrita à Fix-7B.4; nenhuma outra subfase
Fix-7B foi implementada neste trabalho.

---

## Fix-7B.5 — Judge budget e LLM cost consistency (2026-05-15)

### Status
✅ **Concluída** (A-08 P1).

### Resumo da mudança

- `app/infra/llm/pricing.py`: adicionada estimativa determinística de custo de
  judge — `estimate_judge_cost_usd(model, prompt, response, assumed_output_tokens)`,
  `split_provider_model()`, `estimate_tokens()` (heurística ~4 chars/token,
  arredonda para cima) e `DEFAULT_JUDGE_PER_1K` (fallback conservador = tier
  gpt-4.1) para provider/model fora da tabela. `compute_cost_usd` original
  **não foi alterado** (continua usado por `trace_ingest_service`).
- `app/domain/evaluators/llm_judge.py`: `cost_cap_usd` deixou de ser campo
  morto. Estimativa pré-chamada (input real + `max_output_tokens`, default 512);
  se exceder o cap, **bloqueia antes de gastar** e retorna erro estruturado
  `cost_cap_exceeded`. Todos os caminhos de retorno (falha de LLM, parse fail,
  sucesso) agora preenchem `EvaluatorResult.cost_usd` com a estimativa.
- `app/domain/services/eval_service.py`: **sem alteração** — já somava
  `result.cost_usd` em `EvaluationRun.cost_usd`; agora o valor é real.
- `app/domain/services/experiment_service.py`: nova exceção
  `ExperimentBudgetError`. `execute_experiment` aplica o mesmo gate de judge
  budget (pré-check + parada consistente quando o gasto cumulativo de judge
  ultrapassa o budget mid-run). Fecha o bypass onde experiments rodavam
  `llm_judge` via REGISTRY sem gate.
- `app/api/routes_phase5.py`: pré-check 402 espelhando a rota de evaluation
  (quando o rubric do experiment usa `llm_judge` e o budget está esgotado);
  `ExperimentBudgetError` adicionada ao `except` → run `status=error` com
  mensagem segura.

### Contrato final de `cost_cap_usd`

- Tipo: float USD, default `0.01`, por evaluator `llm_judge` (config do rubric).
- Semântica: teto de custo **estimado** de uma única invocação do judge.
- Pré-chamada estima `input (prompt renderizado) + max_output_tokens` (default
  512) usando a tabela de pricing (fallback conservador se model desconhecido).
- Se a estimativa pré-chamada **excede** o cap → **não chama o LLM**; retorna
  `EvaluatorResult(score=0, passed=False, reasoning="cost_cap_exceeded",
  raw_output={error, estimated_cost_usd, cost_cap_usd}, cost_usd=estimativa)`.
- Erro é estável e não vaza stack/SQL/path/segredo.

### Custo real vs estimado

**Estimado**, determinístico. O contrato síncrono de `call_llm` retorna apenas
texto (sem token usage), e chamada de LLM real é proibida em teste. Custo =
`estimate_tokens(prompt)*price_in + estimate_tokens(response)*price_out`
(ou `max_output_tokens` pré-chamada). Mesmo prompt + mesma resposta ⇒ mesmo
custo, portanto testável sem rede.

### Como `EvaluationRun.cost_usd` é preenchido

`llm_judge.run()` seta `EvaluatorResult.cost_usd`; `eval_service.run_evaluation`
soma em `total_cost` e grava em `run.cost_usd`; a rota aplica
`increment_usage(cost_usd=run.cost_usd)`. Evaluators não-LLM continuam custo
`0.0`, logo não consomem judge budget.

### Como o judge budget por plano é aplicado

`Plan.monthly_judge_budget_usd` → `judge_budget_for_org` (fallback seguro 20.0
quando ausente/zero/sem subscription). Gasto do mês = `Σ EvaluationRun.cost_usd`
do projeto no mês corrente. Rota `/evaluations/run`: se o rubric usa `llm_judge`
e `spent >= budget` → **402** `judge_budget_exhausted`. Safety net por evaluator
em `eval_service` mantido. Como o custo agora é real, o budget acumula de runs
reais (antes nunca acumulava).

### Como experiments com `llm_judge` foram protegidos

Pré-check 402 na rota `/experiments/{id}/run` (mesmo gate da evaluation) +
gate defensivo em `execute_experiment` (pré-check e parada cumulativa
mid-run via `ExperimentBudgetError`). Experiments sem `llm_judge`
(`rubric_uses_llm_judge` falso) não são afetados.

### Testes adicionados/alterados

- `tests/test_phase4_rubrics_eval.py`: `TestLlmJudgeCostCap` (cap bloqueia
  antes de gastar / cap permite dentro do limite / erro não vaza internals),
  `test_llm_judge_records_cost_usd_on_evaluation_run`,
  `test_duplicate_llm_judge_evaluation_still_returns_409`.
- `tests/test_phase5_prompts_datasets_experiments.py`: experiment com
  `llm_judge` bloqueado em 402 quando budget esgotado / experiment sem
  `llm_judge` não bloqueado / experiment com `llm_judge` roda quando há budget.
- `tests/test_phase12_quota_eval_storage.py`: **sem alteração** — G-12 já
  cobria block/allow por plano; continua verde com custo real.

### Comandos executados e resultados

Não existe `.venv` neste ambiente; foi criada `apps/api/.venv` com
`python3 -m venv` (Python 3.12) + `pip install -e ".[dev]"`. Os comandos foram
executados via WSL Ubuntu (o repo é montado em `\wsl.localhost`):

```bash
wsl.exe -d Ubuntu -- bash -lc 'cd /home/inovatecjp/rougger/evalops/apps/api && \
  .venv/bin/python -m pytest tests/test_phase4_rubrics_eval.py \
  tests/test_phase5_prompts_datasets_experiments.py \
  tests/test_phase12_quota_eval_storage.py -q --tb=short -p no:warnings'
```
✅ `93 passed in 151.13s`

```bash
wsl.exe -d Ubuntu -- bash -lc 'cd /home/inovatecjp/rougger/evalops/apps/api && \
  .venv/bin/python -m pytest tests -q --tb=short -p no:warnings'
```
✅ `153 passed in 262.30s`

Nota: para respeitar a regra "não rodar a mesma suíte mais de 2 vezes", os
três comandos individuais foram consolidados na regressão focada (1ª execução)
e a regressão ampliada (2ª execução); cada suíte-alvo rodou exatamente 2x.

### Riscos remanescentes

- **Custo estimado, não real**: enquanto o caminho de LLM for síncrono e sem
  token usage, o custo é heurístico (~4 chars/token). Conservador, mas pode
  divergir do faturamento real do provider.
- **Pré-chamada usa `max_output_tokens` assumido (512)**: se a resposta real
  for muito maior, o custo registrado pós-chamada reflete o real estimado, mas
  o gate pré-chamada pode deixar passar um caso de borda; mitigado pelo budget
  mensal que consome o custo real estimado.
- **Mid-run em experiments**: a parada cumulativa usa `result["cost_usd"]` do
  rubric (apenas `llm_judge` gera custo); se um futuro evaluator não-judge
  passar a gerar custo, o tracking precisará discriminar por tipo.

### Pode avançar para Fix-7B.8 ou Fix-7B.6?

✅ **Sim** — entrega restrita à Fix-7B.5 (A-08 P1); nenhuma outra subfase
Fix-7B foi implementada. Regressões de Fix-7B.1/.2/.4 e duplicate-409
continuam verdes.

---

## Fix-7B.8 — Deploy/Alembic/npm audit (2026-05-15)

### Escopo

Subfase restrita aos achados:

- **A-10 P1** — `npm audit` com advisories em Next/PostCSS.
- **A-11 P1** — `docker-compose.prod.yml` desalinhado com Alembic.

Não houve alteração de lógica de negócio backend, soft delete, logout,
quota/concurrency, judge budget, SDK, Redis, cleanup jobs ou redesign de UI.

### Estratégia de Alembic/deploy

`docker-compose.prod.yml` agora usa um job separado `migrate`:

1. `postgres` sobe com healthcheck.
2. `migrate` aguarda Postgres saudável, instala o pacote API + `psycopg` e
   executa `alembic upgrade head`.
3. `api` depende de `migrate: service_completed_successfully`, então uma
   migration com erro impede a API de iniciar.
4. `api` também recebe `EVALOPS_USE_ALEMBIC=1` como guardrail para não cair no
   caminho `create_all` em produção.

Para DBs legados criados antes do Alembic, o runbook permanece: validar schema
Phase 1-6, rodar `alembic stamp 0001_baseline` uma vez e só depois usar o
compose com `upgrade head` automático.

Docs atualizadas:

- `README.md` — notas de deploy/migration.
- `docs/ops/database-migrations.md` — descreve `migrate` service e fallback de
  stamp para DB legado.
- `.env.example` — documenta `EVALOPS_USE_ALEMBIC`, `EVALOPS_EXPORTS_DIR` e
  limits já usados pelo backend.

### npm audit / frontend

Estado inicial:

```bash
cd apps/web && timeout 300 npm audit --omit=dev
```
❌ `2 vulnerabilities (1 moderate, 1 high)`:
`next@15.3.9` com advisories high e `postcss@8.4.31` com advisory moderate.

```bash
cd apps/web && timeout 300 npm audit
```
❌ mesmo resultado: `next` high + `postcss <8.5.10` moderate.

Correção controlada, sem `npm audit fix`:

- `next`: `15.3.9` → `15.5.18`.
- `postcss`: `8.4.31` → `8.5.14` via `overrides.postcss`, porque
  `next@15.5.18` ainda declara `postcss: 8.4.31` como dependência transitiva.

Validação pós-upgrade:

```bash
cd apps/web && timeout 300 npm audit --omit=dev
```
✅ `found 0 vulnerabilities`

```bash
cd apps/web && timeout 300 npm audit
```
✅ `found 0 vulnerabilities`

```bash
cd apps/web && npm ls next postcss
```
✅ `next@15.5.18` com `postcss@8.5.14 overridden`.

### Build/test/typecheck frontend

```bash
cd apps/web && timeout 600 npm run test
```
✅ `29 pass`, `0 fail`.

```bash
cd apps/web && timeout 600 npm run build
```
✅ build Next.js 15.5.18 concluído. Observação não bloqueante:
`app/globals.css` ainda emite warning autoprefixer em `end` vs `flex-end`
(pré-existente/estético, não corrigido nesta subfase para evitar mudança de UI).

```bash
cd apps/web && timeout 600 npx tsc --noEmit
```
✅ typecheck sem erros.

`next build` regenerou `apps/web/next-env.d.ts` adicionando a referência
`./.next/types/routes.d.ts`; nenhum componente, página, layout ou microcopy foi
alterado.

### Alembic smoke

```bash
cd apps/api
rm -f tmp_fix7b_alembic.db
timeout 300 env DATABASE_URL=sqlite:///./tmp_fix7b_alembic.db \
  .venv/bin/alembic upgrade head
```
✅ SQLite efêmero migrou até `0001_baseline`:
`Running upgrade  -> 0001_baseline, baseline schema (Phase 1-6 consolidated).`

O arquivo temporário `tmp_fix7b_alembic.db` foi removido após o smoke.

### Docker Compose config

```bash
docker compose -f docker-compose.prod.yml config
```
⏳ Pendente neste host: `docker` não existe neste WSL2.

```bash
docker-compose -f docker-compose.prod.yml config
```
⏳ Pendente neste host: `docker-compose` também não existe neste WSL2.

Nenhum Docker/Compose foi instalado. A validação estrutural por Compose precisa
ser rodada em ambiente com Docker Desktop/Compose habilitado antes de deploy
real.

Validação complementar sem Docker:

```bash
python3 -c "import yaml, pathlib; data=yaml.safe_load(pathlib.Path('docker-compose.prod.yml').read_text()); print(','.join(sorted(data['services'].keys())))"
```
✅ YAML parseou e listou `api,migrate,postgres`.

### Regressão backend

Não foi rodada suíte backend adicional porque esta subfase não alterou
`app/config.py`, `app/db.py`, `apps/api/alembic/` ou lógica backend. A validação
backend executada foi o smoke Alembic obrigatório em SQLite efêmero.

### Riscos remanescentes

1. **Compose não validado localmente**: Docker/Compose indisponível neste WSL2.
   Rodar `POSTGRES_PASSWORD=... JWT_SECRET=... docker compose -f docker-compose.prod.yml config`
   no ambiente de deploy.
2. **Postgres real não migrado nesta sessão**: não houve deploy real nem smoke
   contra Postgres. Para DB legado, `alembic stamp 0001_baseline` continua
   obrigatório uma única vez antes do compose automático.
3. **API ainda usa imagem Python + install em runtime neste compose**: mantido
   como padrão existente para não ampliar escopo. Produção real deve preferir
   imagem API já buildada.
4. **Autoprefixer warning em CSS**: build passa; a alteração de CSS foi evitada
   por não ser necessária ao fix de audit/deploy.

### Pode avançar para Fix-7B.6 ou Fix-7B.7?

✅ **Sim** — Fix-7B.8 ficou isolada em deploy/Alembic/npm audit; nenhuma outra
subfase Fix-7B foi implementada.

---

## Fix-7B.6.1 — Sanitize evaluator-returned errors (2026-05-16)

### Escopo

Correção curta do blocker P1 identificado na auditoria Fix-7B.6:

- `llm_judge` e `cosine_similarity` retornavam `str(exc)` em
  `EvaluatorResult.reasoning` e `raw_output.error`.
- `json_schema_valid` podia retornar mensagens cruas de parse/schema contendo
  payload, schema ou input sensível.
- Esses campos são persistidos em score/evaluation e podem ser expostos pela
  API de evaluations.

Não houve alteração de soft delete, logout, quota/concurrency, judge budget
além da preservação do contrato existente, Docker/Alembic, SDK, Redis,
cleanup jobs, API key expiration, polling frontend ou UI.

### Correção aplicada

- `apps/api/app/domain/evaluators/llm_judge.py`: falhas de `call_llm` agora
  passam por `safe_message(..., context="llm_judge")`; `reasoning` e
  `raw_output.error` recebem somente texto público seguro. O contrato
  `cost_cap_exceeded`, `cost_usd` e `cost_cap_usd` foi preservado.
- `apps/api/app/domain/evaluators/cosine_similarity.py`: exceções de embedding
  ou cálculo agora passam por `safe_message(..., context="cosine_similarity")`;
  `reasoning` e `raw_output.error` não carregam mais `str(exc)` cru.
- `apps/api/app/domain/evaluators/json_schema_valid.py`: erro de JSON inválido
  retorna o slug `invalid_json`; erro de schema retorna
  `schema_validation_failed`. O schema, a instância e o payload bruto deixam de
  ser expostos em `reasoning`/`raw_output`.
- `apps/api/app/domain/services/eval_service.py`: defesa em profundidade
  sanitiza `EvaluatorResult.reasoning` de resultados falhos e chaves
  `error`/`parse_error`/`schema_error` em `raw_output` antes de persistir.

### Testes adicionados

`apps/api/tests/test_phase4_rubrics_eval.py` cobre:

- `llm_judge` com `call_llm` levantando erro contendo `Traceback`, SQL, path
  local, token `evk_` e bearer token.
- `cosine_similarity` com embedding falhando com erro equivalente.
- `json_schema_valid` com JSON inválido e schema error contendo payload
  sensível.
- API de evaluation persistindo/retornando score sem expor o erro bruto do
  evaluator.

### Comandos executados e resultados

O worktree isolado não possui `.venv`; os testes foram executados a partir do
codigo em `/tmp/evalops-fix-7b6-audit-ab588aa` usando o Python do venv existente
em `/home/rouggerxavier/dev/evalops/apps/api/.venv/bin/python`.

```bash
cd /tmp/evalops-fix-7b6-audit-ab588aa/apps/api && \
  timeout 600 /home/rouggerxavier/dev/evalops/apps/api/.venv/bin/python \
  -m pytest tests/test_phase4_rubrics_eval.py -q --tb=short -p no:warnings
```
✅ `62 passed in 4.50s`

```bash
cd /tmp/evalops-fix-7b6-audit-ab588aa/apps/api && \
  timeout 600 /home/rouggerxavier/dev/evalops/apps/api/.venv/bin/python \
  -m pytest tests/test_phase10_audit_privacy_exports.py -q --tb=short -p no:warnings
```
✅ `25 passed in 3.12s`

```bash
cd /tmp/evalops-fix-7b6-audit-ab588aa/apps/api && \
  timeout 600 /home/rouggerxavier/dev/evalops/apps/api/.venv/bin/python \
  -m pytest tests/test_phase12_quota_eval_storage.py -q --tb=short -p no:warnings
```
✅ `24 passed in 2.98s`

```bash
cd /tmp/evalops-fix-7b6-audit-ab588aa/apps/api && \
  timeout 1200 /home/rouggerxavier/dev/evalops/apps/api/.venv/bin/python \
  -m pytest tests -q --tb=short -p no:warnings
```
✅ `182 passed in 16.51s`

Frontend validation:

- `apps/web/node_modules` não existe neste worktree isolado.
- Nenhum `npm install` foi executado, conforme restrição do prompt.
- `npm run test`, `npm run build` e `npx tsc --noEmit` ficam pendentes para um
  worktree com dependências frontend instaladas.

### Busca final por vazamento

```bash
rg "str\\(exc\\)|repr\\(exc\\)|raw_output.*error|reasoning.*exc|Evaluator error" \
  apps/api/app/domain/evaluators apps/api/app/domain/services/eval_service.py
```

Matches remanescentes justificados:

- `eval_service.py` usa `raw_output={"error": "judge_budget_exhausted"}`:
  slug estruturado e seguro.
- `eval_service.py` usa `reasoning=f"Evaluator error: {safe}"` e
  `raw_output={"error": safe}`: `safe` vem de `safe_message`.
- `cosine_similarity.py` e `llm_judge.py` usam `raw_output={"error": safe}`:
  `safe` vem de `safe_message`.
- `json_schema_valid.py` usa `parse_error`/`schema_error` com slugs seguros.
- `llm_judge.py` ainda mantém `raw_output.raw = raw_text[:500]` quando a
  resposta do LLM não é JSON válido. Esse campo não é exceção nem
  `raw_output.error`; fica como risco residual para auditoria posterior se o
  provider puder ecoar input sensível em respostas inválidas.

### Riscos remanescentes

1. A validação frontend não foi executada neste worktree por ausência de
   `node_modules`.
2. A correção foi aplicada no worktree isolado em detached `ab588aa`, porque o
   worktree principal estava bloqueado por `README.md` dirty e arquivos
   untracked que não deveriam ser tocados sem autorização.
3. `raw_output.raw` de resposta inválida do `llm_judge` continua limitado a
   500 caracteres, mas não foi alterado por estar fora do blocker específico
   `str(exc)`/`raw_output.error`.

### Pode avançar para Fix-7B.7?

✅ **Sim, do ponto de vista backend da Fix-7B.6.1**: o blocker P1 de
`EvaluatorResult.reasoning`/`raw_output.error` foi corrigido e a regressão
backend completa passou. Antes de commit/merge no worktree principal, integrar
esta mudança em `fix-7b` após resolver o bloqueio local de `README.md` dirty.
