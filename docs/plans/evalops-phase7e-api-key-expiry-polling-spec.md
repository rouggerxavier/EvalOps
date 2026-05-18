# EvalOps Phase 7E — ApiKey Expiration / Traces Polling Spec

Date: 2026-05-17
Branch inspected: `main`
HEAD inspected: `2db73ba`
Scope: specification, gap analysis, architecture, UI/UX planning, and future
implementation prompt only. No backend, frontend, SDK, schema, migration,
formatter, `git add`, commit, push, merge, rebase, or amend was performed for
this document.

Primary sources:

- `docs/plans/evalops-phase7-next-steps.md`
- `docs/audits/evalops-phase7-status-after-7bc.md`
- `docs/plans/evalops-phase7-execution-plan.md` as historical context only
- `docs/plans/evalops-phase7d-sdk-dead-letter-spec.md` as recent spec format
- `docs/ops/database-migrations.md`
- `docs/plans/baseline.md`
- `apps/api/app/models.py`
- `apps/api/app/schemas.py`
- `apps/api/app/deps.py`
- `apps/api/app/domain/services/api_key_service.py`
- `apps/api/app/api/routes.py`
- `apps/api/alembic/versions/0001_baseline_schema.py`
- `apps/api/tests/test_phase9_auth_hardening.py`
- `apps/api/tests/test_phase10_audit_privacy_exports.py`
- `apps/api/tests/test_phase11_contracts_ux.py`
- `apps/api/tests/test_phase12_quota_eval_storage.py`
- `apps/web/app/o/[org]/p/[project]/traces/page.tsx`
- `apps/web/app/o/[org]/p/[project]/keys/page.tsx`
- `apps/web/lib/api.ts`
- `apps/web/lib/types.ts`
- `apps/web/lib/actions.ts`
- `apps/web/tests/security.test.mjs`

`AGENTS.md`, `CLAUDE.md`, and repo-local `MEMORY.md` were not present in this
checkout.

## 1. Contexto e objetivo

Phase 7 is no longer the original linear plan. Current `main` already has 7A
Alembic baseline with disposable Postgres smoke recorded, 7C structured
logging/request ID, and 7D SDK dead-letter/replay merged through PR #5. 7B
remains partial/follow-up. 7E is still pending and should be split before
implementation.

7E combines two different concerns in older docs:

- Backend credential lifecycle: add optional `ApiKey.expires_at`, expose it
  through schemas/routes, and reject expired API keys during ingestion auth.
- Frontend traces polling: refresh the traces list automatically without manual
  navigation.

These are not the same risk profile. Backend expiry changes schema, auth
behavior, public API response/request shapes, and requires Alembic revision
`0002` plus a fresh SQLite/Postgres smoke. Frontend polling is product/UX
behavior and can increase API load if it is implemented too broadly.

7A Postgres smoke makes 7E-backend possible now because `0001_baseline` has
already been proven on an empty disposable Postgres DB. That does not authorize
unreviewed schema changes: every new migration still needs its own PR, upgrade
/ downgrade validation, and disposable Postgres smoke.

Do not do in 7E:

- Do not redo 7A, 7C, or 7D.
- Do not mix Redis/distributed rate limiting or cleanup jobs from 7F.
- Do not mix 7B router/service refactor unless a tiny local change is strictly
  required by API key expiry.
- Do not change SDK behavior.
- Do not change public contracts unless needed for expiry.
- Do not rotate keys automatically.
- Do not turn examples into production rules.
- Do not add any migration other than `api_keys.expires_at` in the backend
  split.

## 2. Estado atual encontrado

| Component | Current status | Evidence | Observation |
|---|---|---|---|
| `models.ApiKey` | Exists with `id`, `project_id`, `prefix`, `hash`, `name`, `environment`, `scopes`, `rate_limit_per_minute`, `created_at`, `last_used_at`, `revoked_at`; no `expires_at`. | `apps/api/app/models.py:59-72` | Existing lifecycle is create/list/revoke/last-used only. |
| API key schemas | `ApiKeyCreate` accepts `name`, `environment`, `scopes`; `ApiKeyOut` returns metadata and `revoked_at`; no `expires_at`. | `apps/api/app/schemas.py:38-58` | Public API shape must be extended carefully. |
| `api_key_service.py` | Lists, creates, and revokes keys; create hardcodes rate limit `60`; no expiry validation/persistence. | `apps/api/app/domain/services/api_key_service.py:17-108` | Natural home for create/list expiry wiring. |
| `deps.get_project_from_api_key` | Prefix lookup filters `revoked_at IS NULL`, verifies hash, checks `ingest` scope, then rate limit, then updates `last_used_at`. | `apps/api/app/deps.py:50-86` | Expiry enforcement is absent and should happen before rate limit and `last_used_at`. |
| API key routes | `GET /projects/{project_id}/api-keys`, `POST /projects/{project_id}/api-keys`, and revoke endpoint delegate to service. | `apps/api/app/api/routes.py:153-180` | Router surface is small enough for targeted backend expiry change. |
| Alembic `0001_baseline` | Baseline creates `api_keys` without `expires_at`; `RevokedToken` and `ExportJob` already have `expires_at`. | `apps/api/alembic/versions/0001_baseline_schema.py:155-172`, `:60-67`, `:188-203` | A new revision is required; changing `0001` is prohibited. |
| Frontend keys page | Lists keys, active/revoked counts, create/revoke form; no expiry input, display, filter, or badge. | `apps/web/app/o/[org]/p/[project]/keys/page.tsx:72-87`, `:145-151`, `:277-343`, `:373-419` | If backend exposes expiry, frontend types need to accept it even if UI creation stays unchanged. |
| Frontend traces page | Server component; fetches traces once; has manual refresh link. | `apps/web/app/o/[org]/p/[project]/traces/page.tsx:26-43`, `:77-100` | No auto-refresh, no client component, no pause state, no visibility handling. |
| Frontend types/API | `ApiKey` lacks `expires_at`; `createApiKey` payload lacks expiry; `getTraces` uses `cache: "no-store"` through `requestJson`. | `apps/web/lib/types.ts:91-104`, `apps/web/lib/api.ts:35-45`, `:73-89`, `:115-128` | API helper is already no-store; polling does not require changing fetch cache. |
| Backend tests | API key rate-limit tests exist; no key expiry tests. | `apps/api/tests/test_phase9_auth_hardening.py:95-151`; grep found no API-key expiry test. | Expiry tests should live near auth/rate-limit tests or a new phase 7E test file. |
| Frontend tests | Security tests inspect static contracts; no polling tests or API-key expiry type checks. | `apps/web/tests/security.test.mjs:1-280`, `:526-540` | If frontend polling ships, add static or runtime tests for real polling behavior. |

## 3. Gaps reais da 7E

| Gap | File | Evidence | Impact | Backend split | Frontend split | Expected test |
|---|---|---|---|---|---|---|
| `ApiKey.expires_at` column does not exist. | `apps/api/app/models.py` | `ApiKey` ends at `revoked_at`; no expiry field. | Cannot persist key expiration. | Yes | Type/display only after backend | Model/schema smoke and migration check. |
| Alembic `0002_api_keys_expires_at` does not exist. | `apps/api/alembic/versions/` | Only `0001_baseline_schema.py` exists. | Production/empty DB cannot receive the column through managed migration. | Yes | No | SQLite and disposable Postgres upgrade/downgrade. |
| API key creation does not accept expiry. | `apps/api/app/schemas.py`, `api_key_service.py` | `ApiKeyCreate` has no `expires_at`; service does not set it. | Users cannot create expiring keys through public API. | Yes | Possibly later | Create with future expiry returns it; past expiry rejected if exposed. |
| API key listing/creation output does not expose expiry. | `schemas.py`, `api_key_service.py` | `ApiKeyOut` omits expiry; list/create builds output without it. | UI/API clients cannot see expiry metadata. | Yes | Yes, type-compatible | List/create response includes nullable `expires_at`. |
| Auth does not reject expired keys. | `deps.py` | Auth checks revoked, scopes, rate limit, last-used; no expiry check. | Expired credentials would remain valid after adding column unless enforcement is added. | Yes | No | Expired key returns 401. |
| Expired keys would currently update `last_used_at` and consume rate limit if expiry were checked too late. | `deps.py` | Rate limit is checked at lines 70-76 and `last_used_at` set at 78-80. | Incorrect audit/lifecycle semantics and unnecessary limiter noise. | Yes | No | Expired key does not update `last_used_at`; does not consume limiter if verifiable. |
| Expired versus revoked precedence is undefined. | `deps.py`, `api_key_service.py` | Revoked keys are filtered out before hash verification. | Error details must avoid leaking key existence/lifecycle state. | Yes | No | Revoked+expired remains unauthorized without secret leak. |
| Frontend key types do not include expiry. | `apps/web/lib/types.ts` | `ApiKey` has `created_at` and `revoked_at` only. | If backend returns `expires_at`, TS code should tolerate/render it. | Optional in backend PR if web package is part of contract | Yes | Static type/source test or build. |
| Keys UI has no expiry input/display. | `keys/page.tsx` | Create form has name/environment/scopes only; table has created/revoked status only. | Users cannot manage expiry from UI. | No, unless backend PR also updates minimal display | Follow-up | Display badge and create input tests if included. |
| Traces page has no auto-refresh/polling. | `traces/page.tsx` | Manual refresh link only; no `useEffect`, `setInterval`, `router.refresh`, or `visibilitychange` in app code. | Live ingestion demos require manual refresh; polling risk remains unaddressed. | No | Yes | Polling ticks only when visible and enabled. |
| Polling scope is not defined. | `traces/page.tsx`, product docs | Existing page has tabs, filters, cursor paging, empty state. | Naive polling can refresh empty/static pages and increase API load. | No | Yes | Tests for pause/visibility/interval and no useless calls. |

## 4. Decisão de split recomendada

### Opção A — 7E-backend primeiro, frontend polling depois

Backend:

- Add nullable `ApiKey.expires_at`.
- Add Alembic `0002_api_keys_expires_at`.
- Extend schemas/services/routes without breaking existing create/list/revoke.
- Enforce expiry in `get_project_from_api_key`.
- Add backend tests and migration smoke.
- Update docs.

Frontend polling:

- Move to `7E-frontend` or post-MVP follow-up.
- Keep a planning section in this spec but avoid coupling it to a migration PR.

### Opção B — 7E unificada

One PR changes backend expiry and frontend polling together.

Risk: combines migration/auth behavior with client runtime UX, making review and
rollback harder. A frontend polling regression should not block credential
expiry, and a migration issue should not block a purely UX change.

### Opção C — só frontend polling

Implement polling without key expiry.

Risk: leaves the named backend credential lifecycle gap open even though 7A has
unblocked the migration path. Useful only if a demo explicitly needs live trace
updates before security lifecycle work.

Recommended decision: choose **Option A**. Implement 7E-backend first and keep
frontend polling as a named follow-up unless the user explicitly prioritizes
the live traces UX. This gives smaller blast radius, an isolated migration PR,
clearer tests, and simpler rollback.

## 5. Backend 7E — ApiKey.expires_at spec

### Modelo/schema

- Add `expires_at: datetime | None` to `ApiKey`.
- Use `DateTime(timezone=True)`, consistent with `created_at`,
  `last_used_at`, `revoked_at`, `ExportJob.expires_at`, and
  `RevokedToken.expires_at`.
- Default `None` means no expiration.
- Preserve current behavior for existing keys: no expiry, still usable unless
  revoked or otherwise invalid.
- Add Alembic migration `0002_api_keys_expires_at`.
- Downgrade removes only the `api_keys.expires_at` column.
- Do not edit `0001_baseline_schema.py`.

Timezone rule:

- Use UTC-aware datetimes at API boundaries and in Python comparisons.
- Be careful with SQLite returning naive datetimes in some paths. Existing docs
  already recorded naive/aware issues around export expiry. Future
  implementation should normalize both sides before comparison instead of
  relying on a database-specific behavior.

### Contratos

Recommended contract:

- `POST /v1/projects/{project_id}/api-keys` accepts optional `expires_at`.
- `expires_at: null` or omitted means no expiration.
- Key without expiration remains allowed.
- Future `expires_at` is accepted.
- Past or equal-to-now `expires_at` is rejected with 422.
- `GET /v1/projects/{project_id}/api-keys` returns nullable `expires_at`.
- Create response returns nullable `expires_at` plus the one-shot `key`.
- Revoke endpoint behavior remains unchanged and idempotent.
- Expired API key on ingestion returns 401.
- Recommended `detail`: keep `unauthorized` for expired keys to avoid exposing
  whether a key exists, was revoked, or expired. The historical plan mentioned
  `api_key_expired`, but current auth surfaces mostly use generic
  `unauthorized`/`forbidden` and the project already has error-sanitization
  guardrails. If a product/debug need requires `api_key_expired`, that should
  be an explicit user decision before implementation.
- No response, header, audit payload, log, or frontend query param may reveal
  the raw key secret.

Compatibility:

- Existing clients that omit `expires_at` must continue working.
- Existing response clients should tolerate a new nullable field.
- API key prefix/hash generation remains unchanged.
- Scopes remain generic strings, not hardcoded examples.
- Rate-limit response remains 429 with `Retry-After` for non-expired valid
  keys that exceed quota.

### Enforcement

Recommended order in `get_project_from_api_key`:

1. Require `X-EvalOps-Key`.
2. Resolve prefix and verify hash among non-revoked candidates.
3. If no candidate matches, return 401.
4. Check `expires_at` before scope, rate limit, and `last_used_at`.
5. If expired, return 401 and do not update `last_used_at`.
6. Do not consume rate-limit budget for expired keys.
7. Check `ingest` scope and return 403 for valid non-expired keys missing the
   scope.
8. Check rate limit.
9. Update `last_used_at`.
10. Load project and reject archived/missing project as today.

Revoked + expired:

- Revoked keys are currently excluded from candidates before hash verification.
  Keep that behavior. A key that is both revoked and expired should remain
  indistinguishable from an invalid/revoked key to callers.

Audit/logging:

- Do not add a new audit event for every expired-key attempt in initial 7E; it
  could create noisy write amplification on hot ingestion paths.
- Existing request logging must continue not to include API key headers.
- If future abuse monitoring needs expired-key attempts, design it as a
  rate-limited security signal, not a default audit write per request.

## 6. Migration 0002 plan

Expected file:

- `apps/api/alembic/versions/0002_api_keys_expires_at.py`

Expected revision metadata:

- `revision = "0002_api_keys_expires_at"`
- `down_revision = "0001_baseline"`
- `branch_labels = None`
- `depends_on = None`

Expected upgrade:

- Use `op.batch_alter_table("api_keys")` for SQLite-safe behavior.
- Add `sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True)`.
- Do not add an index unless a measured query requires it. Auth lookup uses
  prefix/hash first; expiry is checked only after selected key verification.
- Do not touch `revoked_at`, `last_used_at`, `rate_limit_per_minute`, scopes,
  prefixes, hashes, or projects.

Expected downgrade:

- Use `op.batch_alter_table("api_keys")`.
- Drop only `expires_at`.

Required smoke:

- SQLite fresh DB: `alembic upgrade head`, `alembic current`, `alembic downgrade -1`,
  and upgrade again.
- Disposable Postgres fresh DB: same upgrade/current/downgrade/upgrade loop.
- Do not use a production database.
- Do not run migration against a legacy create_all DB before stamping. If a DB
  already has the Phase 1-6 schema created outside Alembic, follow
  `docs/ops/database-migrations.md`: verify shape, run
  `alembic stamp 0001_baseline`, then `alembic upgrade head`.

## 7. Frontend 7E — polling spec

Current UI:

- `traces/page.tsx` is a server component.
- It calls `resolveProject` and `getTraces` once during render.
- It provides tabs, filters, cursor pagination, export link, and a manual
  refresh link with a `RefreshCw` icon.
- `getTraces` already uses the shared no-store fetch path.
- There is no client polling component today.

UI/UX assessment for polling:

- Polling should not be a silent load multiplier. The trace list is potentially
  a repeated operational surface, and each open tab can cause backend reads.
- Manual refresh should remain. It is predictable, cheap, and accessible.
- If polling is implemented, it must be a real stateful control, not an empty
  button or decorative spinner.
- Polling should pause when the document is hidden.
- Polling should pause when the user disables auto-refresh.
- Polling should avoid cursor-paged views unless explicitly intended; auto
  refreshing page 2 can confuse users when rows move between pages.
- Polling should not fire on an empty/no-trace page by default unless a user has
  explicitly enabled it for onboarding/demo. Otherwise the page creates calls
  before any SDK is connected.
- A conservative default interval is 15-30 seconds. Prefer 30 seconds unless a
  demo or pending-evaluation workflow needs tighter feedback.
- UI should show concise feedback such as last refreshed time, paused state, or
  a small refresh-in-progress indicator. Avoid large explanatory copy.
- Keep the traces page primarily server-rendered. If implemented, add a small
  client component whose only responsibility is auto-refresh controls around
  `router.refresh()`.
- Do not add SWR/react-query just for this first polling behavior.

Recommended minimal future behavior:

- Add a client `TracesAutoRefresh` component under the traces route.
- Props: `enabledByDefault`, `intervalMs`, `disabledReason?`.
- Use `useRouter().refresh()` on an interval only when:
  - auto-refresh is enabled;
  - `document.visibilityState === "visible"`;
  - no refresh is currently in flight;
  - current route has no `cursor` query param;
  - optionally, there are rows or an explicit opt-in flag is set.
- Listen to `visibilitychange` to pause/resume cleanly.
- Preserve the manual refresh link/button.
- Keep button dimensions stable and use the existing `RefreshCw` icon.
- Add a compact toggle or icon button with accessible label.
- Use fake timers or a source-level test to prove `setInterval`,
  `router.refresh`, `visibilitychange`, and cleanup are present.

Recommendation: keep this as `7E-frontend` follow-up after backend expiry, not
in the migration/auth PR.

## 8. Fora de escopo

- Redis/distributed rate limit.
- Cleanup jobs for `RevokedToken`, `ExportJob`, exports, or expired API keys.
- SDK changes.
- Structured logging/request ID.
- SDK dead-letter/replay.
- 7B service/router refactor beyond tiny local edits required for expiry.
- Billing/plan changes.
- Key rotation.
- Secret recovery.
- Wide UI redesign.
- Polling in overview, evaluations, exports, datasets, prompts, rubrics, or
  trace detail.
- Any migration other than nullable `api_keys.expires_at`.

## 9. Plano de implementação futura

Recommended next implementation: **7E-backend first**.

1. Create a dedicated branch.
   - Files: none initially.
   - Risk: accidental work on `main`.
   - Validation: branch name and clean worktree.

2. Add Alembic migration `0002_api_keys_expires_at`.
   - Files: `apps/api/alembic/versions/0002_api_keys_expires_at.py`.
   - Risk: wrong `down_revision`, non-reversible downgrade, SQLite-incompatible
     DDL.
   - Validation: inspect revision metadata and local SQLite upgrade/downgrade.

3. Update backend model and schemas.
   - Files: `apps/api/app/models.py`, `apps/api/app/schemas.py`.
   - Risk: timezone mismatch, public response breakage.
   - Validation: schema tests for omitted/null/future/past expiry.

4. Update API key service.
   - Files: `apps/api/app/domain/services/api_key_service.py`.
   - Risk: accepting past expiry, omitting expiry from list/create output,
     logging secrets in audit payload.
   - Validation: create/list tests; audit payload remains secret-free.

5. Enforce expiry in dependency.
   - Files: `apps/api/app/deps.py`.
   - Risk: checking too late and consuming rate limit/updating `last_used_at`;
     returning too-specific errors.
   - Validation: expired key 401, no last-used update, future/no-expiry works.

6. Add/adjust backend tests.
   - Likely files: new `apps/api/tests/test_phase7e_api_key_expiry.py` or
     targeted additions to `test_phase9_auth_hardening.py` and
     `test_phase10_audit_privacy_exports.py`.
   - Risk: broad fixture churn.
   - Validation: targeted API key/auth/contract tests pass.

7. Run migration smokes.
   - SQLite: fresh upgrade/current/downgrade/upgrade.
   - Postgres: disposable DB upgrade/current/downgrade/upgrade.
   - Risk: false confidence from SQLite-only validation.
   - Validation: record exact commands/results in docs.

8. Run targeted backend validations.
   - API key/auth tests.
   - Contract/security tests affected by response shape.
   - Do not run global formatters.

9. Code review before commit.
   - Confirm no frontend polling slipped into backend PR.
   - Confirm no SDK/Redis/cleanup changes.

### 7E-frontend follow-up

If frontend polling is approved after backend expiry:

1. Add a small client auto-refresh component under the traces route.
2. Wire it into `traces/page.tsx` without moving the full page to client-side
   data fetching.
3. Preserve manual refresh and existing filters/tabs/pagination.
4. Pause on hidden tab and user-disabled state.
5. Avoid polling cursor pages by default.
6. Add source-level or jsdom/fake timer tests.
7. Run frontend test/build/typecheck available in the environment.

## 10. Critérios de aceite

Backend expiry:

- `apps/api/alembic/versions/0002_api_keys_expires_at.py` exists and is
  reversible.
- `api_keys.expires_at` is nullable.
- Existing keys and newly created keys without expiry keep working.
- Future-expiring keys work before expiry.
- Expired keys are rejected on ingestion.
- Expired keys do not update `last_used_at`.
- Expired keys do not consume API key rate limit if this is verifiable through
  existing limiter tests.
- Past expiry on creation returns 422 if creation exposes `expires_at`.
- List/create responses include `expires_at: null|string`.
- Revoke remains unchanged.
- Raw key secret is still shown only once and never appears in URLs, logs,
  audit payloads, or error messages.
- SQLite migration smoke passes.
- Disposable Postgres migration smoke passes.
- Existing API key/auth/contract tests pass.

Frontend polling, if later included:

- Polling is real and calls `router.refresh()`, not a placeholder control.
- Manual refresh remains available.
- Polling pauses while `document.hidden` / non-visible.
- Polling can be disabled by the user.
- Polling avoids cursor-paged views or documents why it is safe.
- UI shows compact state/feedback without cluttering the operational table.
- Tests/build/typecheck pass for the web package.

## 11. Decisões pendentes para o usuário

Recommended answers are included to unblock the next prompt.

| Question | Recommendation |
|---|---|
| Should 7E start with backend expiry only? | Yes. Implement `7E-backend` first. |
| Should `expires_at` be optional on create? | Yes. Omitted/null means no expiration and preserves compatibility. |
| Should keys without expiration be allowed? | Yes for now; forcing expiry would be a policy/product change. |
| Should past/equal expiry be rejected on create? | Yes, return 422. |
| Should expired API keys return 401 or 403? | 401 with generic `unauthorized` is recommended to avoid lifecycle leakage. Use `api_key_expired` only if the user explicitly prioritizes debuggability over indistinguishability. |
| Should expired keys update `last_used_at`? | No. |
| Should expired keys consume rate limit? | No. |
| Should list/create expose `expires_at`? | Yes, nullable. |
| Should the keys UI create expiry in the backend PR? | No, unless the user explicitly wants UI scope. The web types can be updated for compatibility; full UI creation can follow. |
| Should frontend polling enter now? | No. Keep it as `7E-frontend` follow-up unless a live-demo need overrides. |
| If polling enters later, what interval? | 30 seconds default; 15 seconds only for explicit demo/pending-workflow need. |

Blocking decision before implementation:

- Confirm whether expired ingestion should return generic `401 unauthorized` or
  explicit `401 api_key_expired`.

## 12. Próximo prompt recomendado

Use this prompt next only after documental review approval:

```text
Você está no projeto EvalOps em /home/rouggerxavier/dev/evalops.

Tarefa: implementar somente 7E-backend — ApiKey.expires_at com migration 0002.
NÃO implementar frontend polling neste prompt.
NÃO alterar SDK.
NÃO misturar Redis/cleanup 7F.
NÃO refatorar 7B além do mínimo local necessário.
NÃO rodar formatters globais.
NÃO fazer git add, commit, push, merge, rebase ou amend.

Antes de alterar:
1. Confirmar branch main, worktree limpo, HEAD sincronizado com origin/main.
2. Ler AGENTS.md/CLAUDE.md/MEMORY.md se existirem.
3. Ler docs/plans/evalops-phase7e-api-key-expiry-polling-spec.md.
4. Ler docs/ops/database-migrations.md.
5. Ler backend relacionado a ApiKey: models, schemas, api_key_service, deps, routes, 0001_baseline, testes de auth/API key.

Escopo:
- Criar apps/api/alembic/versions/0002_api_keys_expires_at.py com down_revision 0001_baseline.
- Adicionar ApiKey.expires_at nullable DateTime(timezone=True).
- ApiKeyCreate aceita expires_at opcional.
- ApiKeyOut/ApiKeyCreateOut retornam expires_at nullable.
- create_key persiste expires_at e rejeita expires_at no passado/agora com 422.
- list_keys retorna expires_at.
- get_project_from_api_key rejeita key expirada antes de scope/rate-limit/last_used_at.
- Expired key deve retornar 401 genericamente como unauthorized, salvo decisão explícita diferente.
- Expired key não deve atualizar last_used_at nem consumir rate limit.
- Revoke continua igual.
- Secret não pode vazar em URL, log, audit payload, header ou erro.

Testes obrigatórios:
- key sem expiração aceita ingest.
- key com expiração futura aceita ingest.
- key expirada rejeita ingest com 401.
- key expirada não atualiza last_used_at.
- key expirada não consome rate limit se verificável.
- criação com expires_at passado/agora retorna 422.
- list/create retornam expires_at.
- regressão de create/revoke/audit API key.
- SQLite migration upgrade/downgrade.
- Postgres descartável migration upgrade/downgrade.

Validações:
- git diff --check.
- testes backend focados em API key/auth/contratos.
- SQLite Alembic smoke.
- Postgres descartável Alembic smoke.

Ao final, relatar arquivos alterados, comandos/resultados, riscos e não fazer commit.
```

If the user chooses to include frontend polling anyway, split it into a second
prompt named `7E-frontend traces polling` after backend expiry is merged.
