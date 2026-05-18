# EvalOps Phase 7E — ApiKey Expiration / Traces Polling Spec

Date: 2026-05-17
Branch inspected: `main`
HEAD inspected: `b4ffed2`
Scope: specification, gap analysis, architecture, UI/UX planning, and post-merge
status tracking. The original pre-implementation backend plan is preserved as
historical context, but 7E-backend has now shipped. No backend, frontend, SDK,
schema, migration, formatter, `git add`, commit, push, merge, rebase, or amend
was performed for this documentation update.

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
- `apps/api/alembic/versions/0002_api_keys_expires_at.py`
- `apps/api/tests/test_phase7e_api_key_expiry.py`
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
logging/request ID, 7D SDK retry/dead-letter/replay merged through PR #5, and
7E-backend merged through PR #6. 7B remains partial/follow-up. 7E-frontend
polling remains pending.

7E combines two different concerns in older docs:

- Backend credential lifecycle: add optional `ApiKey.expires_at`, expose it
  through schemas/routes, and reject expired API keys during ingestion auth.
- Frontend traces polling: refresh the traces list automatically without manual
  navigation.

These are not the same risk profile. Backend expiry changed schema, auth
behavior, and public API response/request shapes through Alembic revision
`0002`. Frontend polling is product/UX behavior and can increase API load if it
is implemented too broadly.

PR #6 implemented the backend split:

- Merge commit: `b4ffed2ded2cd01c78cdbd23ab710ea149aa8f7d`.
- Backend commit: `2ff9070 feat(evalops): add api key expiration`.
- Migration: `apps/api/alembic/versions/0002_api_keys_expires_at.py`.
- Model/schema/service/auth: `ApiKey.expires_at` is persisted, exposed, and
  enforced in `get_project_from_api_key`.
- Expired keys return generic 401 and are rejected before scope, rate-limit, and
  `last_used_at` update.
- Tests: `apps/api/tests/test_phase7e_api_key_expiry.py`.
- Remote CI and Vercel checks passed before merge.

This documentation pass did not rerun product tests or migrations and did not
touch production data. Every future migration still needs its own PR, upgrade /
downgrade validation, and disposable Postgres smoke.

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
| `models.ApiKey` | Includes nullable `expires_at`. | `apps/api/app/models.py` | Backend storage gap closed by PR #6. |
| API key schemas | `ApiKeyCreate`, `ApiKeyOut`, and `ApiKeyCreateOut` include nullable `expires_at`; past/equal expiry is rejected. | `apps/api/app/schemas.py` | Public API shape is extended compatibly for omitted/null expiry. |
| `api_key_service.py` | Lists, creates, and revokes keys; create persists nullable expiry and list/create return it. | `apps/api/app/domain/services/api_key_service.py` | Backend lifecycle gap closed. |
| `deps.get_project_from_api_key` | Verifies key, rejects expired keys with generic 401 before scope, rate limit, and `last_used_at`. | `apps/api/app/deps.py` | Expired keys do not get treated as valid ingestion attempts. |
| API key routes | `GET /projects/{project_id}/api-keys`, `POST /projects/{project_id}/api-keys`, and revoke endpoint delegate to service. | `apps/api/app/api/routes.py:153-180` | Router surface is small enough for targeted backend expiry change. |
| Alembic `0002_api_keys_expires_at` | Adds nullable `api_keys.expires_at` on top of `0001_baseline`; downgrade drops only that column. | `apps/api/alembic/versions/0002_api_keys_expires_at.py` | `0001` remains immutable. |
| Frontend keys page | Lists keys, active/revoked counts, create/revoke form; no expiry input, display, filter, or badge. | `apps/web/app/o/[org]/p/[project]/keys/page.tsx:72-87`, `:145-151`, `:277-343`, `:373-419` | If backend exposes expiry, frontend types need to accept it even if UI creation stays unchanged. |
| Frontend traces page | Server component; fetches traces once; has manual refresh link. | `apps/web/app/o/[org]/p/[project]/traces/page.tsx:26-43`, `:77-100` | No auto-refresh, no client component, no pause state, no visibility handling. |
| Frontend types/API | `ApiKey` lacks `expires_at`; `createApiKey` payload lacks expiry; `getTraces` uses `cache: "no-store"` through `requestJson`. | `apps/web/lib/types.ts:91-104`, `apps/web/lib/api.ts:35-45`, `:73-89`, `:115-128` | API helper is already no-store; polling does not require changing fetch cache. |
| Backend tests | Key expiry tests exist. | `apps/api/tests/test_phase7e_api_key_expiry.py` | This documentation pass did not rerun them. |
| Frontend tests | Security tests inspect static contracts; no polling tests or API-key expiry type checks. | `apps/web/tests/security.test.mjs:1-280`, `:526-540` | If frontend polling ships, add static or runtime tests for real polling behavior. |

## 3. Gaps reais da 7E

| Gap | File | Evidence | Impact | Backend split | Frontend split | Expected test |
|---|---|---|---|---|---|---|
| `ApiKey.expires_at` column was absent. | `apps/api/app/models.py` | PR #6 added nullable `expires_at`. | Backend gap closed. | Done | Type/display follow-up only if needed | Covered by phase7E backend tests and migration review. |
| Alembic `0002_api_keys_expires_at` was absent. | `apps/api/alembic/versions/` | PR #6 added `0002_api_keys_expires_at`. | Backend gap closed; production was not migrated by this docs pass. | Done | No | Future migrations still need their own smoke. |
| API key creation did not accept expiry. | `apps/api/app/schemas.py`, `api_key_service.py` | PR #6 added nullable create/list response support and validation. | Backend gap closed. | Done | Possibly later for UI creation | Create with future expiry returns it; past/equal expiry rejected. |
| Auth did not reject expired keys. | `deps.py` | PR #6 rejects expired keys before scope/rate limit/last-used. | Backend gap closed. | Done | No | Expired key returns generic 401. |
| Expired versus revoked precedence needed leak-safe behavior. | `deps.py`, `api_key_service.py` | Revoked keys remain indistinguishable from invalid; expired keys also use generic 401. | Backend gap closed. | Done | No | Revoked/expired states avoid secret/lifecycle leakage. |
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

Decision taken: **Option A**. 7E-backend shipped first through PR #6. Frontend
polling remains a named follow-up unless the user explicitly prioritizes the
live traces UX.

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

Implemented contract:

- `POST /v1/projects/{project_id}/api-keys` accepts optional `expires_at`.
- `expires_at: null` or omitted means no expiration.
- Key without expiration remains allowed.
- Future `expires_at` is accepted.
- Past or equal-to-now `expires_at` is rejected with 422.
- `GET /v1/projects/{project_id}/api-keys` returns nullable `expires_at`.
- Create response returns nullable `expires_at` plus the one-shot `key`.
- Revoke endpoint behavior remains unchanged and idempotent.
- Expired API key on ingestion returns 401.
- Expired-key auth keeps the response generic to avoid exposing whether a key
  exists, was revoked, or expired.
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

## 6. Migration 0002 status

Implemented file:

- `apps/api/alembic/versions/0002_api_keys_expires_at.py`

Implemented revision metadata:

- `revision = "0002_api_keys_expires_at"`
- `down_revision = "0001_baseline"`
- `branch_labels = None`
- `depends_on = None`

Implemented upgrade:

- Use `op.batch_alter_table("api_keys")` for SQLite-safe behavior.
- Add `sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True)`.
- Do not add an index unless a measured query requires it. Auth lookup uses
  prefix/hash first; expiry is checked only after selected key verification.
- Do not touch `revoked_at`, `last_used_at`, `rate_limit_per_minute`, scopes,
  prefixes, hashes, or projects.

Implemented downgrade:

- Use `op.batch_alter_table("api_keys")`.
- Drop only `expires_at`.

Required smoke for future migration work:

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

7E-backend is complete after PR #6. The checklist below is preserved as
historical context for what was implemented and reviewed in that split; do not
reuse it as the next prompt.

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

Backend expiry (done in PR #6):

- [x] `apps/api/alembic/versions/0002_api_keys_expires_at.py` exists and is
  reversible.
- [x] `api_keys.expires_at` is nullable.
- [x] Existing keys and newly created keys without expiry keep working.
- [x] Future-expiring keys work before expiry.
- [x] Expired keys are rejected on ingestion.
- [x] Expired keys do not update `last_used_at`.
- [x] Expired keys do not consume API key rate limit if this is verifiable through
  existing limiter tests.
- [x] Past expiry on creation returns 422 if creation exposes `expires_at`.
- [x] List/create responses include `expires_at: null|string`.
- [x] Revoke remains unchanged.
- [x] Raw key secret is still shown only once and never appears in URLs, logs,
  audit payloads, or error messages.
- [ ] New production migration has not been run by this documentation pass.
- [ ] This documentation pass did not rerun product tests or migration smokes.

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
| Should expired API keys return 401 or 403? | Done: generic 401 to avoid lifecycle leakage. |
| Should expired keys update `last_used_at`? | No. |
| Should expired keys consume rate limit? | No. |
| Should list/create expose `expires_at`? | Yes, nullable. |
| Should the keys UI create expiry in the backend PR? | No, unless the user explicitly wants UI scope. The web types can be updated for compatibility; full UI creation can follow. |
| Should frontend polling enter now? | Still pending. Keep it as `7E-frontend` follow-up unless a live-demo need overrides. |
| If polling enters later, what interval? | 30 seconds default; 15 seconds only for explicit demo/pending-workflow need. |

No blocking backend decision remains for 7E-backend. The remaining decision is
whether live traces UX justifies implementing `7E-frontend` polling before 7F.

## 12. Próximo prompt recomendado

Use this prompt next only after documental review approval if product/demo/live
UX is the priority:

```text
Você está no projeto EvalOps em /home/rouggerxavier/dev/evalops.

Tarefa: implementar somente 7E-frontend — traces polling/auto-refresh.
NÃO alterar backend.
NÃO alterar SDK.
NÃO criar migration.
NÃO misturar Redis/cleanup 7F.
NÃO refatorar 7B.
NÃO rodar formatters globais.
NÃO fazer git add, commit, push, merge, rebase ou amend.

Antes de alterar:
1. Confirmar branch main, worktree limpo, HEAD sincronizado com origin/main.
2. Ler AGENTS.md/CLAUDE.md/MEMORY.md se existirem.
3. Ler docs/plans/evalops-phase7e-api-key-expiry-polling-spec.md.
4. Ler docs/plans/evalops-phase7-next-steps.md.
5. Ler apps/web/app/o/[org]/p/[project]/traces/page.tsx e helpers web
   relacionados a traces.

Escopo:
- Adicionar pequeno componente client para auto-refresh usando router.refresh().
- Preservar refresh manual.
- Permitir pausar/desabilitar auto-refresh.
- Pausar quando document.visibilityState não for visible.
- Evitar polling em páginas com cursor por padrão.
- Manter feedback compacto de estado/último refresh.
- Não adicionar SWR/react-query só para este comportamento.

Testes/validação:
- source-level ou jsdom/fake timers cobrindo setInterval, router.refresh,
  visibilitychange e cleanup.
- frontend test/build/typecheck disponível no ambiente.

Validações:
- git diff --check.
- git diff --stat.
- git status --short.

Ao final, relatar arquivos alterados, comandos/resultados, riscos e não fazer commit.
```

If the priority is operational production readiness instead, pick 7F Redis rate
limit + cleanup jobs before this polling work.
