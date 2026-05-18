# EvalOps Phase 7 status after 7E-backend merge

Date: 2026-05-17
Branch inspected: `main`
HEAD inspected: `b4ffed2`
Original status-pass snapshot: `f13f24c`; latest documentation verification:
`b4ffed2`.
Scope: documentation reconciliation only. No backend, frontend, SDK, test, infra,
or lockfile changes were made as part of this status pass.

Sources used:

- `git log --oneline --decorate -20` on `main`.
- Current code under `apps/api`, `apps/web`, `packages/sdk-python`, and
  `docker-compose*.yml`.
- PR #6 merge commit `b4ffed2ded2cd01c78cdbd23ab710ea149aa8f7d`.
- Existing docs:
  `docs/plans/evalops-remediation-roadmap.md`,
  `docs/plans/baseline.md`,
  `docs/plans/evalops-phase7-execution-plan.md`,
  `docs/plans/evalops-fix-7b-execution-plan.md`,
  `docs/audits/evalops-full-codebase-audit.md`,
  `docs/ops/database-migrations.md`.

`AGENTS.md` and `CLAUDE.md` were not present in this checkout.

---

## 1. Current Phase 7 State

| Subphase | Real status | Evidence | Remaining gaps | Next step |
|---|---|---|---|---|
| 7A Alembic / migrations | Postgres smoke approved on disposable DB | `618e511` added `apps/api/alembic/`, `0001_baseline_schema.py`, `EVALOPS_USE_ALEMBIC` startup path, and `docs/ops/database-migrations.md`; `b6c962d` updated `docker-compose.prod.yml` with a dedicated `migrate` job; 2026-05-17 Docker Desktop + WSL integration resolved the prior local blocker and a disposable `postgres:16-alpine` container (`evalops-postgres-alembic-smoke`, DB `evalops_alembic_smoke`, port `55432`) accepted connections; after installing missing local venv dependency `psycopg[binary]` (`psycopg`/`psycopg-binary` 3.3.4), `alembic upgrade head` reached `0001_baseline`, `alembic current` returned `0001_baseline (head)`, `alembic downgrade base` passed, and `alembic upgrade head` passed again. The disposable container was removed. | `Base.metadata.create_all` and `ensure_schema_compatibility()` still exist for dev/test fallback; legacy DB `stamp` was not tested in this smoke; future schema changes still need new revisions, their own PR, and their own smoke. | 7A no longer blocks new revisions; after PR #6, the next choice is 7E-frontend polling vs 7F Redis/cleanup. |
| 7B service extraction / ownership helper | partial | `618e511` added `app/ownership.py`, `trace_ingest_service.py`, `export_service.py`, `api_key_service.py`; `routes.py` and `routes_phase6.py` now call these services. | `routes_phase5.py` still has `_project_or_404` wrappers and call sites; routers remain large (`routes.py` 421 lines, `routes_phase5.py` 499 lines, `routes_phase6.py` 185 lines); some services still own framework exceptions/commits. | Treat as 7B follow-up, preferably after deployment blockers or when touching related routers for real bugs. |
| 7C structured logging / request_id | done | `9e9a517` added `app/logging_config.py`, `app/request_id.py`, middleware in `app/main.py`, context updates in `app/deps.py`, and `tests/test_phase13_logging_request_id.py`. | No gap found against the original 7C objective. Operational validation in the target deploy environment is still useful. | Do not reimplement; only harden if runtime logging issues appear. |
| 7D SDK retry / dead-letter | done | `40cf27a` delivered retry/drop reliability and `4ab910b` / PR #5 delivered SDK dead-letter/replay. | No current Phase 7 blocker recorded for SDK reliability. | Do not reimplement unless a fresh SDK review finds a concrete regression. |
| 7E-backend `ApiKey.expires_at` | done | PR #6 merged at `b4ffed2ded2cd01c78cdbd23ab710ea149aa8f7d`; `2ff9070` added `ApiKey.expires_at`, schemas/service wiring, `0002_api_keys_expires_at`, generic 401 expiry enforcement in `get_project_from_api_key`, and `apps/api/tests/test_phase7e_api_key_expiry.py`. Remote CI and Vercel checks passed before merge. | Production migration was not run in this documentation pass; this pass did not run product tests. | Keep as done; future migrations still need their own smoke and review. |
| 7E-frontend traces polling | pending / follow-up | `traces/page.tsx` still has manual refresh only; no client polling component or auto-refresh state was implemented by PR #6. | Live trace UX still requires manual refresh; polling load/visibility/cursor behavior remains undecided. | Choose this next if product/demo/live status UX is the priority. |
| 7F Redis rate limit / cleanup jobs | pending / follow-up | `docker-compose.yml` has Redis and `REDIS_URL`, but `rate_limit_service.py` is in-memory; no Redis client usage found. `RevokedToken` and `ExportJob.expires_at` exist, but no cleanup script/job was found. | Distributed rate limiting absent; cleanup of expired revoked tokens and export files/rows absent. | Keep as post-MVP unless deploying multi-worker or export/revoked-token volume is growing. |

---

## 2. Already Implemented

Structured logging and request correlation are implemented on `main` by
`9e9a517 feat(evalops): add structured request logging`.

Observed files:

- `apps/api/app/logging_config.py` defines a JSON formatter and `evalops.access`
  logger.
- `apps/api/app/request_id.py` stores request, user, and org context in
  `ContextVar`s.
- `apps/api/app/main.py` emits `request.start` and `request.end`, echoes
  `X-Request-ID`, and measures `latency_ms`.
- `apps/api/tests/test_phase13_logging_request_id.py` covers request ID behavior
  and JSON log formatting.

SDK reliability is already partly implemented by
`40cf27a fix(evalops): harden sdk execution reliability`, and the named
dead-letter/replay gap was later completed by `4ab910b feat(evalops): add sdk
dead-letter replay`.

Observed behavior in `packages/sdk-python/evalops/uploader.py`:

- `max_retries` and `retry_backoff_s` are configurable.
- `_send()` retries HTTP `408`, `429`, `5xx`, and exceptions.
- Non-retryable `4xx` return `False` without retry.
- `flush()` and `shutdown()` are bounded by computed join timeout behavior.
- Queue-full fallback attempts direct send before incrementing drops.
- `dropped_count` exposes the drop counter.
- PR #5 added the dead-letter/replay layer on top of that reliability work.

Service extraction and ownership centralization are partially implemented by
`618e511 refactor(evalops): extract services and ownership helpers`.

Observed files:

- `apps/api/app/ownership.py`
- `apps/api/app/domain/services/trace_ingest_service.py`
- `apps/api/app/domain/services/export_service.py`
- `apps/api/app/domain/services/api_key_service.py`

Alembic/deploy work is materially present:

- `apps/api/alembic/versions/0001_baseline_schema.py`
- `apps/api/alembic/versions/0002_api_keys_expires_at.py`
- `apps/api/app/main.py` with `EVALOPS_USE_ALEMBIC`.
- `docs/ops/database-migrations.md`.
- `docker-compose.prod.yml` with `migrate` service and `EVALOPS_USE_ALEMBIC=1`.

API key expiration is implemented by PR #6:

- `ApiKey.expires_at` exists and is exposed through create/list response shapes.
- `create_key` persists nullable `expires_at` and schema validation rejects
  past/equal expiry.
- `get_project_from_api_key` rejects expired keys before scope, rate limit, and
  `last_used_at` update.
- Expired keys use a generic 401 response.
- `apps/api/tests/test_phase7e_api_key_expiry.py` covers the backend behavior.

Fix-7B also absorbed several old blockers that should not be reopened as Phase 7
work without fresh evidence:

- SQLite test isolation was documented as resolved in `baseline.md`.
- Deployment Alembic wiring and npm audit alignment were addressed in `b6c962d`.
- SDK retry/drop reliability was addressed in `40cf27a`.
- Error sanitization and frontend contract cleanup have separate commits in
  the current `main` history.

---

## 3. Resolved And Still Required Before Calling Phase 7 Complete

Resolved blocker:

- 7A Postgres migration smoke: approved on 2026-05-17 in a disposable
  `postgres:16-alpine` container after Docker Desktop + WSL integration resolved
  the prior environment blocker. The first Alembic attempt failed only because
  `psycopg` was missing from the local API venv; installing
  `psycopg[binary]>=3,<4` installed `psycopg`/`psycopg-binary` 3.3.4 and
  unblocked the smoke. `alembic upgrade head`, `alembic current`,
  `alembic downgrade base`, and a second `alembic upgrade head` all passed
  against DB `evalops_alembic_smoke`; `current` reported
  `0001_baseline (head)`. The disposable container was removed.

Resolved since the earlier status pass:

- 7D dead-letter/replay: merged through PR #5 after the original retry/drop
  reliability work.
- 7E-backend `ApiKey.expires_at`: merged through PR #6.

Product/UX or governance items:

- 7E frontend traces polling: still absent; likely polish unless demos depend on
  live updates.
- 7B follow-up: remove remaining `_project_or_404` wrappers in phase 5 routers
  and continue reducing router/service coupling where it supports a bug fix.

Operational follow-up:

- 7F Redis/distributed rate limit: required before multi-worker/multi-instance
  rate limiting is a hard requirement.
- 7F cleanup jobs: required before expired revoked tokens and exports grow enough
  to matter operationally.

---

## 4. Reinterpreted 7D

The old Phase 7 plan said "SDK retry + dead-letter". That is no longer accurate
as an implementation prompt because `40cf27a` implemented a meaningful
retry/drop reliability layer and PR #5 completed dead-letter/replay.

Do not ask the next agent to redo:

- controlled retries;
- retryable HTTP `408`, `429`, `5xx`, and network exceptions;
- permanent `4xx` without retry;
- bounded `flush()` / `shutdown()`;
- queue-full fallback;
- `dropped_count`;
- existing SDK tests around these behaviors.

Updated 7D should be treated as complete for Phase 7. Any future SDK work should
start from a fresh review finding, not from the stale pre-PR #5 gap list.

---

## 5. Recommended Next Order From Current `main`

The old order `7A -> 7B -> 7C -> 7D -> 7E -> 7F` is stale because 7A/7C/7D and
7E-backend already landed, while 7B remains partial. The updated order should
be:

### 1. 7A Postgres migration verification

Objective: prove the existing Alembic path works outside SQLite before adding
more schema work.

Status: completed on 2026-05-17 with disposable Postgres.

Likely files for any future update: docs only for recording evidence, then
`docs/ops/database-migrations.md` and `docs/plans/baseline.md`.

Risks: false confidence if only SQLite is tested; legacy databases may require
`alembic stamp 0001_baseline` instead of `upgrade head`.

Required tests/commands:

- `cd apps/api && DATABASE_URL=<postgres-url> alembic upgrade head`
- `cd apps/api && DATABASE_URL=<postgres-url> alembic current`
- optional rollback smoke on disposable DB: `alembic downgrade base`

Acceptance:

- Empty Postgres upgrade reaches `0001_baseline`. Done on disposable DB
  `evalops_alembic_smoke`.
- Existing/legacy stamping path is documented if used. Not exercised by this
  disposable smoke.
- No production DB is mutated without explicit operator approval.

Review before commit: yes.

Suggested model/effort: GPT-5.5 high or equivalent, because migration mistakes
are expensive.

### 2. 7E-frontend traces polling, if live UX is priority

Objective: add bounded auto-refresh without coupling it to backend expiry,
Redis, cleanup, or SDK work.

Likely files:

- `apps/web/app/o/[org]/p/[project]/traces/page.tsx`
- possible small client component under the traces route
- frontend source-level or jsdom/fake-timer tests

Risks: polling every open tab, refreshing cursor pages unexpectedly, or hiding
the existing manual refresh affordance.

Required tests:

- auto-refresh ticks only when enabled and visible;
- interval cleanup happens on unmount;
- manual refresh remains available;
- cursor pages are skipped or explicitly handled.

Acceptance:

- Small client component around `router.refresh()`, not a full page rewrite.
- Pausable control with compact state feedback.
- No backend, SDK, migration, Redis, or cleanup changes.

Review before commit: yes.

Suggested model/effort: GPT-5.4/GPT-5.5 medium.

### 3. 7F Redis/cleanup as operational work

Objective: support multi-worker rate limiting and cleanup expired records/files
when the deployment shape requires it.

Likely files if implemented later:

- `apps/api/app/domain/services/rate_limit_service.py`
- `apps/api/scripts/cleanup.py` or equivalent
- `apps/api/pyproject.toml`
- `docker-compose*.yml`
- targeted backend tests

Risks: new Redis dependency changes deploy behavior; cleanup can delete useful
exports if retention is not agreed.

Required tests if implemented:

- memory backend regressions;
- Redis backend if Redis/fakeredis is available;
- cleanup removes only expired `RevokedToken`/`ExportJob` rows and files.

Acceptance:

- Default dev/test remains in-memory.
- Production Redis behavior has a clear fallback policy.
- Cleanup is idempotent and dry-run capable.

Review before commit: yes.

Suggested model/effort: GPT-5.5 high for Redis/cleanup safety.

### 4. 7B follow-up only when it supports active work

Objective: remove remaining ownership wrappers and reduce router coupling where
that improves maintainability for a real change.

Risks: broad refactor without business value; accidental contract changes.

Required tests:

- existing phase 5 tests;
- ownership denial/archived project tests if wrappers are removed.

Acceptance:

- `_project_or_404` no longer appears in productive API code, or any remaining
  occurrence is documented with a reason.
- No endpoint status/schema behavior changes.

Review before commit: yes.

Suggested model/effort: GPT-5.4 high.

### 5. Release notes / Phase 7 closure docs

Objective: close Phase 7 only after the remaining follow-ups are either shipped
or explicitly moved out with rationale.

Do not mark Phase 7 100% complete while 7E-frontend, 7F, and 7B follow-up remain
open.

---

## 6. Updated Global Completion Criteria

Blocking for Phase 7 completion:

- [x] 7A: Alembic path verified on SQLite and disposable Postgres.
- [ ] 7B: service extraction remains partial/follow-up with remaining wrappers
      listed.
- [x] 7C: structured JSON request logging with request ID exists in `9e9a517`.
- [x] 7D: SDK retry/drop and dead-letter/replay are merged.
- [x] 7E-backend: key expiration is merged in PR #6.
- [ ] 7E-frontend: polling is implemented or moved to a named follow-up with
      rationale.
- [ ] 7F: Redis/cleanup implemented or moved to post-MVP with a trigger
      condition.

Verification commands/checks:

- Git state: `git status --short` must be clean before implementation PRs.
- 7A: `cd apps/api && alembic upgrade head` on disposable SQLite/Postgres.
- 7B: `rg -n "_project_or_404" apps/api/app`.
- 7C: `cd apps/api && .venv/bin/python -m pytest tests/test_phase13_logging_request_id.py -q --tb=short -p no:warnings`.
- 7D: `cd packages/sdk-python && python -m pytest tests -q --tb=short`.
- 7E-backend: already has `apps/api/tests/test_phase7e_api_key_expiry.py`.
- 7E-frontend: frontend test/build if polling is kept.
- 7F: targeted rate-limit and cleanup tests.

Already satisfied by commits:

- `9e9a517` satisfies 7C.
- `40cf27a` satisfies the retry/drop part of 7D.
- `4ab910b` / PR #5 satisfies dead-letter/replay for 7D.
- `b4ffed2` / PR #6 satisfies 7E-backend.
- `618e511` satisfies most of 7A and part of 7B.
- `b6c962d` satisfies the production compose migration wiring noted in the
  full-codebase audit.

---

## 7. Decisions And Gaps Discovered

Decisions needed:

- Should Phase 7 require Postgres smoke before any new schema work? Recommended:
  yes, and every new migration must still land in its own PR with its own smoke.
- Should traces polling remain in Phase 7, or move to UX polish after the MVP?
- What retention policy should cleanup use for exports, and should cleanup delete
  files immediately after `expires_at` or with a grace window?
- What should the Redis failure policy be in production: fail closed, fail open,
  or fallback to memory with warning?

Inconsistencies found:

- The older roadmap still described 7B-7F as pending even though current `main`
  contains 7B/7C and part of 7D.
- The old 7D prompt would cause duplicate retry/dead-letter work unless
  rewritten.
- Redis is present in dev compose, but rate limiting remains in-memory.
- The old 7B acceptance of zero `_project_or_404` is not met in
  `routes_phase5.py`, so 7B must stay partial rather than done.

Items that may leave Phase 7:

- Frontend traces polling can be post-MVP unless live dashboard UX is required.
- Redis distributed rate limit can be post-MVP while production remains
  single-worker/single-instance.
- Cleanup jobs can be post-MVP with an explicit operational trigger.

---

## 8. Recommended Next Operational Prompt

Recommended next prompt if product/demo/live UX is the priority:

```text
Prompt for Codex: implement only 7E-frontend traces polling/auto-refresh,
without changing backend, SDK, migrations, Redis, or cleanup.

Start from main at b4ffed2. Read AGENTS.md/CLAUDE.md/MEMORY.md if present,
then read:
- docs/plans/evalops-phase7-next-steps.md
- docs/plans/evalops-phase7e-api-key-expiry-polling-spec.md
- apps/web/app/o/[org]/p/[project]/traces/page.tsx
- apps/web/lib/api.ts
- apps/web/tests/security.test.mjs

Goal:
- add a small client auto-refresh control around router.refresh();
- preserve manual refresh;
- pause when hidden or disabled;
- avoid cursor pages by default;
- add focused frontend validation available in the environment;
- do not commit/push.
```
