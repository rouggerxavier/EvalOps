# EvalOps Phase 7 status after 7B/7C merge

Date: 2026-05-17
Branch inspected: `main`
HEAD inspected: `f13f24c`
Scope: documentation reconciliation only. No backend, frontend, SDK, test, infra,
or lockfile changes were made as part of this status pass.

Sources used:

- `git log --oneline --decorate -20` on `main`.
- Current code under `apps/api`, `apps/web`, `packages/sdk-python`, and
  `docker-compose*.yml`.
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
| 7A Alembic / migrations | partial | `618e511` added `apps/api/alembic/`, `0001_baseline_schema.py`, `EVALOPS_USE_ALEMBIC` startup path, and `docs/ops/database-migrations.md`; `b6c962d` updated `docker-compose.prod.yml` with a dedicated `migrate` job. | Postgres smoke remains pending in docs; `Base.metadata.create_all` and `ensure_schema_compatibility()` still exist for dev/test fallback; future schema changes still need new revisions. | Run focused 7A verification on Postgres and document go/no-go before adding new schema work. |
| 7B service extraction / ownership helper | partial | `618e511` added `app/ownership.py`, `trace_ingest_service.py`, `export_service.py`, `api_key_service.py`; `routes.py` and `routes_phase6.py` now call these services. | `routes_phase5.py` still has `_project_or_404` wrappers and call sites; routers remain large (`routes.py` 421 lines, `routes_phase5.py` 499 lines, `routes_phase6.py` 185 lines); some services still own framework exceptions/commits. | Treat as 7B follow-up, preferably after deployment blockers or when touching related routers for real bugs. |
| 7C structured logging / request_id | done | `9e9a517` added `app/logging_config.py`, `app/request_id.py`, middleware in `app/main.py`, context updates in `app/deps.py`, and `tests/test_phase13_logging_request_id.py`. | No gap found against the original 7C objective. Operational validation in the target deploy environment is still useful. | Do not reimplement; only harden if runtime logging issues appear. |
| 7D SDK retry / dead-letter | partial | `40cf27a` changed `packages/sdk-python/evalops/uploader.py` and `packages/sdk-python/tests/test_sdk.py`; current code has controlled retries, 408/429/5xx/exception retry behavior, bounded shutdown/flush logic, queue-full fallback, and `dropped_count`. | No local dead-letter directory, no `replay_dead_letter(...)`, no Retry-After honoring, and no jitter found. `packages/sdk-python/evalops/__init__.py` does not export replay. | Do gap analysis and implement only dead-letter/replay plus Retry-After/jitter if still desired; preserve the reliability fixes from `40cf27a`. |
| 7E `ApiKey.expires_at` / frontend polling | pending | `ApiKey` has `created_at`, `last_used_at`, and `revoked_at`, but no `expires_at`; `expires_at` hits in current code are `RevokedToken`, `ExportJob`, and frontend export type fields. `traces/page.tsx` has a manual refresh link only. | No key expiration model/schema/API enforcement; no Alembic revision for key expiry; no traces polling/auto-refresh component. | Decide whether key expiration is MVP-blocking. If yes, implement backend-only first; keep polling as follow-up unless UX requires it. |
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
`40cf27a fix(evalops): harden sdk execution reliability`.

Observed behavior in `packages/sdk-python/evalops/uploader.py`:

- `max_retries` and `retry_backoff_s` are configurable.
- `_send()` retries HTTP `408`, `429`, `5xx`, and exceptions.
- Non-retryable `4xx` return `False` without retry.
- `flush()` and `shutdown()` are bounded by computed join timeout behavior.
- Queue-full fallback attempts direct send before incrementing drops.
- `dropped_count` exposes the drop counter.

Service extraction and ownership centralization are partially implemented by
`618e511 refactor(evalops): extract services and ownership helpers`.

Observed files:

- `apps/api/app/ownership.py`
- `apps/api/app/domain/services/trace_ingest_service.py`
- `apps/api/app/domain/services/export_service.py`
- `apps/api/app/domain/services/api_key_service.py`

Alembic/deploy work is materially present:

- `apps/api/alembic/versions/0001_baseline_schema.py`
- `apps/api/app/main.py` with `EVALOPS_USE_ALEMBIC`.
- `docs/ops/database-migrations.md`.
- `docker-compose.prod.yml` with `migrate` service and `EVALOPS_USE_ALEMBIC=1`.

Fix-7B also absorbed several old blockers that should not be reopened as Phase 7
work without fresh evidence:

- SQLite test isolation was documented as resolved in `baseline.md`.
- Deployment Alembic wiring and npm audit alignment were addressed in `b6c962d`.
- SDK retry/drop reliability was addressed in `40cf27a`.
- Error sanitization and frontend contract cleanup have separate commits in
  the current `main` history.

---

## 3. Still Required Before Calling Phase 7 Complete

Blocking or near-blocking items:

- 7A Postgres migration smoke: run `alembic upgrade head` and rollback/smoke on
  a real Postgres environment, then record the result.
- 7D dead-letter/replay gap: implement local dead-letter files and
  `replay_dead_letter(...)` only if SDK telemetry durability remains part of
  Phase 7.

Product/UX or governance items:

- 7E `ApiKey.expires_at`: add model/schema/API enforcement and an Alembic
  revision if credential expiration is required for the MVP.
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
as an implementation prompt because `40cf27a` already implemented a meaningful
retry/drop reliability layer.

Do not ask the next agent to redo:

- controlled retries;
- retryable HTTP `408`, `429`, `5xx`, and network exceptions;
- permanent `4xx` without retry;
- bounded `flush()` / `shutdown()`;
- queue-full fallback;
- `dropped_count`;
- existing SDK tests around these behaviors.

Updated 7D should be:

1. Inspect the current SDK retry behavior and tests to avoid regressions.
2. Add local dead-letter persistence for batches that are dropped after final
   failure, probably under `~/.evalops/dead/` or `EVALOPS_DEAD_LETTER_DIR`.
3. Add `replay_dead_letter(...)` as a public SDK helper if the file format is
   accepted.
4. Add focused tests for dead-letter write and replay.
5. Validate whether `Retry-After` and jitter are worth adding now; they are
   not present in current code.

Decision needed: should client-side validation errors (`4xx` other than
`408/429`) be written to dead-letter? The original plan said no; that avoids
amplifying bad local payloads but means some rejected telemetry is intentionally
dropped.

---

## 5. Recommended Next Order From Current `main`

The old order `7A -> 7B -> 7C -> 7D -> 7E -> 7F` is stale because 7A/7B/7C and
part of 7D already landed. The updated order should be:

### 1. 7A Postgres migration verification

Objective: prove the existing Alembic path works outside SQLite before adding
more schema work.

Likely files: docs only for this pass, then `docs/ops/database-migrations.md`
and `docs/plans/baseline.md` for the recorded result.

Risks: false confidence if only SQLite is tested; legacy databases may require
`alembic stamp 0001_baseline` instead of `upgrade head`.

Required tests/commands:

- `cd apps/api && DATABASE_URL=<postgres-url> alembic upgrade head`
- `cd apps/api && DATABASE_URL=<postgres-url> alembic current`
- optional rollback smoke on disposable DB: `alembic downgrade base`

Acceptance:

- Empty Postgres upgrade reaches `0001_baseline`.
- Existing/legacy stamping path is documented if used.
- No production DB is mutated without explicit operator approval.

Review before commit: yes.

Suggested model/effort: GPT-5.5 high or equivalent, because migration mistakes
are expensive.

### 2. 7D updated SDK dead-letter/replay gap

Objective: finish only the missing part of the original 7D.

Likely files:

- `packages/sdk-python/evalops/uploader.py`
- `packages/sdk-python/evalops/__init__.py`
- `packages/sdk-python/tests/test_sdk.py`
- optional SDK README if public API changes

Risks: breaking flush/shutdown guarantees from `40cf27a`; writing secrets/PII to
disk without an explicit retention/security decision.

Required tests:

- final failed retry writes a dead-letter file;
- `replay_dead_letter(...)` re-submits and handles success/failure;
- permanent `4xx` behavior is explicit and tested;
- existing retry/drop tests remain green.

Acceptance:

- Existing reliability tests still pass.
- Dead-letter path is configurable.
- Replay API is documented or intentionally kept internal.

Review before commit: yes.

Suggested model/effort: GPT-5.4/GPT-5.5 medium.

### 3. Decide 7E scope split

Objective: decide whether `ApiKey.expires_at` is MVP-blocking and whether
frontend polling belongs in Phase 7 or post-MVP.

Likely files if implemented later:

- `apps/api/app/models.py`
- `apps/api/app/schemas.py`
- `apps/api/app/domain/services/api_key_service.py`
- `apps/api/app/deps.py`
- `apps/api/alembic/versions/0002_api_keys_expires_at.py`
- `apps/web/app/o/[org]/p/[project]/traces/page.tsx`

Risks: adding schema before validating Postgres migration path; polling causing
unnecessary API traffic.

Required tests if implemented:

- expired key rejected;
- future/no-expiry key accepted;
- past expiry rejected on create/update;
- polling pauses when tab hidden if frontend scope is kept.

Acceptance:

- Backend key expiration can be shipped independently.
- Frontend polling is either implemented with guardrails or explicitly moved to
  follow-up.

Review before commit: yes.

Suggested model/effort: GPT-5.4/GPT-5.5 medium.

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

### 5. 7F Redis/cleanup as post-MVP operational work

Objective: support multi-worker rate limiting and cleanup expired records/files.

Risks: new Redis dependency changes deploy behavior; cleanup can delete useful
exports if retention is not agreed.

Required tests:

- memory backend regressions;
- Redis backend if Redis/fakeredis is available;
- cleanup removes only expired `RevokedToken`/`ExportJob` rows and files.

Acceptance:

- Default dev/test remains in-memory.
- Production Redis behavior has a clear fallback policy.
- Cleanup is idempotent and dry-run capable.

Review before commit: yes.

Suggested model/effort: GPT-5.5 high for Redis/cleanup safety.

---

## 6. Updated Global Completion Criteria

Blocking for Phase 7 completion:

- [ ] 7A: Alembic path verified on SQLite and Postgres, or Postgres gap
      explicitly accepted as out-of-scope for the current deployment.
- [ ] 7B: service extraction status is either completed or explicitly marked as
      partial follow-up with remaining wrappers listed.
- [x] 7C: structured JSON request logging with request ID exists in `9e9a517`.
- [ ] 7D: either dead-letter/replay is implemented, or Phase 7 explicitly
      narrows 7D to the retry/drop reliability already delivered in `40cf27a`.
- [ ] 7E: key expiration and polling are implemented or moved to a named
      follow-up with rationale.
- [ ] 7F: Redis/cleanup implemented or moved to post-MVP with a trigger
      condition.

Verification commands/checks:

- Git state: `git status --short` must be clean before implementation PRs.
- 7A: `cd apps/api && alembic upgrade head` on disposable SQLite/Postgres.
- 7B: `rg -n "_project_or_404" apps/api/app`.
- 7C: `cd apps/api && .venv/bin/python -m pytest tests/test_phase13_logging_request_id.py -q --tb=short -p no:warnings`.
- 7D: `cd packages/sdk-python && python -m pytest tests -q --tb=short`.
- 7E: backend tests for expired API keys; frontend test/build if polling is kept.
- 7F: targeted rate-limit and cleanup tests.

Already satisfied by commits:

- `9e9a517` satisfies 7C.
- `40cf27a` satisfies the retry/drop part of 7D.
- `618e511` satisfies most of 7A and part of 7B.
- `b6c962d` satisfies the production compose migration wiring noted in the
  full-codebase audit.

---

## 7. Decisions And Gaps Discovered

Decisions needed:

- Should Phase 7 require Postgres smoke before any new schema work? Recommended:
  yes.
- Should 7D write permanent `4xx` failures to dead-letter, or only retry-exhausted
  transient failures? The old plan implied no dead-letter for permanent client
  errors.
- Should `ApiKey.expires_at` remain Phase 7 or move to post-MVP credential
  governance?
- Should traces polling remain in Phase 7, or move to UX polish after the MVP?
- What retention policy should cleanup use for exports, and should cleanup delete
  files immediately after `expires_at` or with a grace window?
- What should the Redis failure policy be in production: fail closed, fail open,
  or fallback to memory with warning?

Inconsistencies found:

- The older roadmap still described 7B-7F as pending even though current `main`
  contains 7B/7C and part of 7D.
- The old 7D prompt would cause duplicate retry work unless rewritten.
- `expires_at` exists in export/revoked-token models, but not in `ApiKey`.
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

Recommended next prompt:

```text
Prompt for Codex: verify and document 7A Postgres Alembic readiness, without
implementing product code.

Start from main at f13f24c. Read AGENTS.md/CLAUDE.md if present, then read:
- docs/ops/database-migrations.md
- docs/plans/baseline.md
- docs/audits/evalops-phase7-status-after-7bc.md
- docker-compose.prod.yml
- apps/api/alembic/versions/0001_baseline_schema.py

Goal:
- run or plan a disposable Postgres Alembic smoke (`alembic upgrade head`,
  `alembic current`, optional `downgrade base`) depending on local Docker/Postgres
  availability;
- update docs only with evidence;
- do not implement backend/frontend/SDK code;
- do not commit/push.

If Postgres is unavailable, document the exact blocked command and environment
needed, then stop with a review-ready docs diff.
```
