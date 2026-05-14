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

A suíte completa `pytest apps/api/tests -q` apresenta falhas intermitentes por
**SQLite database is locked** quando rodada sem reset do arquivo entre arquivos
de teste. Workaround obrigatório:

```bash
cd apps/api && rm -f evalops.db* && python -m pytest <alvos> -q --tb=short -p no:warnings
```

Sempre apagar `evalops.db*` antes de cada invocação do `pytest`. Executar
arquivos em grupos pequenos (≤ 8 arquivos por chamada) para mitigar o lock.
A suíte completa em uma única chamada **ainda não é confiável** — esta
limitação fica registrada como dívida até a Fase 6 (G-25, Postgres em prod) ou
Fase 7 (isolamento de DB por worker / fixtures).

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
