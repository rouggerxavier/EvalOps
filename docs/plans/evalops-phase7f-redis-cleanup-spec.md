# EvalOps Phase 7F — Redis Rate Limit / Cleanup Jobs Spec

Date: 2026-05-18
Base branch: `main`
Base HEAD: `63da5af` (`Merge pull request #8 from rouggerxavier/phase-7f-a-rate-limit-abstraction`)
`origin/main`: `63da5af` (in sync)
Status source: `docs/audits/evalops-phase7-status-after-7bc.md`,
`docs/plans/evalops-phase7-next-steps.md`,
`docs/plans/evalops-remediation-roadmap.md`,
`docs/plans/baseline.md`,
`docs/ops/database-migrations.md`.

Author note: this document was refreshed after PR #8 merged 7F-A. This refresh
is documentation/status only. No backend, frontend, SDK, schema, migration,
infra, product test, or formatter change was made in this pass. The
agent-framework-router was available and routed the work as documentation/status
reconciliation with documentary review before commit.

`AGENTS.md`, `CLAUDE.md`, and a repo-local `MEMORY.md` were not present in this
checkout.

---

## 1. Context and objective

### Current Phase 7 state

Phase 7 is integrated into `main` except for the operational tail:

- 7A Alembic/migrations — done; disposable Postgres smoke approved.
- 7B service extraction/ownership — partial; opportunistic follow-up only.
- 7C structured logging/request_id — done.
- 7D SDK retry/dead-letter/replay — done (through PR #5).
- 7E-backend `ApiKey.expires_at` — done (PR #6, migration `0002`).
- 7E-frontend traces polling — done (PR #7, merge `f44ed19`).
- 7F-A rate limiter abstraction — done (PR #8, merge `63da5af`).
- 7F-B Redis backend — pending.
- 7F-C cleanup jobs — pending.
- 7F-D final ops docs — pending/follow-up.

7F as a whole is **not complete** until Redis/distributed limiting, cleanup
services, and final ops docs are implemented or explicitly deferred.

### Why 7F is the standard next candidate after 7E

7E closed the last *product-visible* gap of Phase 7 (key expiry + traces
polling). What remains is **operational readiness for multi-worker /
horizontal scale**: the rate limiter is per-process in-memory and there is no
retention/cleanup for expired `RevokedToken` and `ExportJob` rows or their
files. These are the named "what's left for later" items in the Phase 4 and
Phase 2 sections of `evalops-remediation-roadmap.md` and the explicit next
step in both the audit and next-steps docs.

### Readiness vs product feature

7F is **operational readiness**, not a user-facing feature:

- No new endpoint contract for end users.
- No new UI.
- No new SDK behavior.
- The observable behavior of rate limiting and exports must stay equivalent
  from the client's point of view; only the *backing mechanism* and *data
  hygiene* change.

### Why 7F must be spec-first

- It touches a security-adjacent path (`deps.get_project_from_api_key`,
  `routes_auth.login`) where a wrong failure policy either lets abuse through
  (fail-open misuse) or locks out legitimate traffic (fail-closed on a Redis
  blip).
- It introduces an external dependency (Redis) that must remain optional for
  dev/test.
- Cleanup deletes rows and files; deletion must be idempotent, bounded, and
  safe (no path traversal, no symlink follow, no deletion outside the export
  dir).

A reviewed spec lets us lock the failure/retention/safety decisions before any
deletion or external-dependency code exists.

### Explicit non-goals / what must not be redone

- Do not reopen 7A / 7C / 7D / 7E without a new concrete finding.
- Do not fold in 7B architectural cleanup (router/service coupling,
  `_project_or_404` dedup) — separate, opportunistic track.
- Do not change `apps/web` (frontend).
- Do not change `packages/sdk-python` (SDK).
- Do not create a migration unless a strictly required missing field is
  discovered. (Section 2 confirms none is required: `RevokedToken.expires_at`
  and `ExportJob.expires_at` already exist.)
- Do not promise full production multi-worker until Redis and the prod deploy
  path (which today runs `--workers 1` and has no Redis service) are validated.

---

## 2. Current state found

Evidence is `path:line` from the inspected checkout at HEAD `63da5af`.

| Component | Current state | Evidence | Observation |
|---|---|---|---|
| API-key rate limit | In-memory sliding window behind 7F-A backend abstraction, single process | `apps/api/app/domain/services/rate_limit_service.py:39` `RateLimiterBackend`; `:57` `InMemoryRateLimiter`; `:102` module `_backend`; `:114` `check_api_key_rate_limit` | Keyed by `ApiKey.id` through `api_key_rate_limit_key()` (not raw key — already safe). Window 60s, ceiling = `per_minute` or `DEFAULT_API_KEY_PER_MINUTE=60`. |
| Rate-limit enforcement point | `deps.get_project_from_api_key` | `apps/api/app/deps.py:82` calls `check_api_key_rate_limit(selected.id, selected.rate_limit_per_minute)`; 429 + `Retry-After` at `:83-88` | This is the only call site for API-key limiting. Contract = HTTP 429 + `Retry-After` header + `detail="too_many_requests"`. |
| Login brute-force limit | In-memory window behind the same 7F-A backend abstraction, single process | `rate_limit_service.py:128` `check_login_rate_limit`, `:134` `record_login_failure`, `:139` `reset_login_failures`; consumed in `apps/api/app/api/routes_auth.py` | Keyed by normalized `email|ip`, window 300s, ceiling 5 *failures*; success clears bucket. 429 + `Retry-After` + `detail="too_many_attempts"`. |
| `ApiKey.rate_limit_per_minute` | Persisted column, default 60 | `apps/api/app/models.py:69`; surfaced in `apps/api/app/schemas.py:65`; defaulted by `api_key_service.py:55` | Per-key ceiling already in schema. No change needed. |
| Rate-limit storage | Per-process heap, lost on restart; abstraction now exists | `rate_limit_service.py:1-17` docstring says 7F-A preserves single-process behavior and leaves Redis/distributed storage for 7F-B | 7F-A reduced implementation risk but did **not** solve multi-worker consistency. |
| Redis client / config | **None in code** | No `redis` import anywhere under `apps/api`; `apps/api/app/config.py` has no Redis getter; no `REDIS_URL` read in code | Redis is referenced only by dev compose env (next row). |
| Redis in dev compose | Service present, env wired, **unused by app** | `docker-compose.yml`: `redis: image: redis:7-alpine`, `api.environment.REDIS_URL: redis://redis:6379/0`, `api.depends_on: [postgres, redis]` | Dev compose advertises Redis but the app never reads it. Divergence between infra intent and code. |
| Redis in prod compose | **Absent** | `docker-compose.prod.yml` has no `redis` service; api runs `uvicorn … --workers 1` | Prod is single-worker today; no Redis service to point at. Multi-worker is not yet a live configuration. |
| Runtime config module | `apps/api/app/config.py`, lazy env getters | `config.py:26` `max_body_bytes`, `:30` `max_spans_per_trace`, `:34` `exports_dir` (honors `EVALOPS_EXPORTS_DIR`, else `apps/api/storage/exports`) | No `settings.py`/`pydantic-settings`; convention = `os.environ` lazy getter with `_positive_int`-style helpers. New Redis config should follow this pattern. |
| `RevokedToken` | Model present, written on logout, read on auth | `models.py:437-449` (pk `jti`, `expires_at` indexed, `revoked_at`); written `routes_auth.py:261-269`; read `deps.py:36` | `expires_at` is indexed → cleanup query is cheap. **No cleanup exists** for rows past `expires_at`. Table grows unbounded. |
| Logout / revocation flow | Idempotent denylist insert | `routes_auth.py:232-273`; legacy tokens without `jti` are no-ops by design (`:258-259`) | Deleting rows where `expires_at < now` is safe: an expired JWT is already rejected by `decode_access_token`, so the denylist row is redundant after `expires_at`. |
| `ExportJob` | Model present; 7-day expiry set | `models.py:349-363` (`file_path` nullable, `expires_at` nullable, `status`); `export_service.py:105` sets `expires_at = utcnow() + timedelta(days=7)` | **No cleanup exists** for expired jobs or their files. |
| Export file storage | Single dir, absolute | `export_service.py:96` writes `exports_dir()/<job.id>.jsonl`; dir from `config.py:34` (`EVALOPS_EXPORTS_DIR` or `apps/api/storage/exports`), `mkdir(parents=True, exist_ok=True)` | Files named `<job.id>.jsonl` (job id from `new_id("expj")`); deletion target is well-bounded and predictable. |
| Export download | 410 on expiry, FileResponse | `apps/api/app/api/routes_phase6.py:97-126`; 410 if `expires_at` passed (`:106-113`), 404 if missing file (`:122`), no local path exposed (test `test_phase10:347`) | Expired jobs already return 410; cleanup is hygiene (reclaim disk + bound table), not a correctness fix. |
| Expiry fields | Both target tables already have them | `RevokedToken.expires_at` `models.py:448`; `ExportJob.expires_at` `models.py:360` | **No migration required for 7F.** |
| Startup / lifespan | No background work | `apps/api/app/main.py:45-53` lifespan: `configure_logging()` then alembic-or-`create_all`; no scheduler, no `asyncio.create_task`, no `BackgroundTasks` | There is no existing in-app scheduler to extend; introducing one is a deliberate decision, not an incremental change. |
| Migrations | `0001_baseline`, `0002_api_keys_expires_at` | `docs/ops/database-migrations.md:52-58`; `revoked_tokens`/`export_jobs` are in the baseline 26-table set (`:182-188`) | `head` = `0002`. 7F adds no revision. |
| Tests | Rate-limit abstraction covered; revoked/export behavior covered elsewhere | `apps/api/tests/test_phase7f_rate_limit_service.py` covers `InMemoryRateLimiter`, `RateLimitResult`, `reset_all`, non-secret API-key identifier, and facade delegation; `apps/api/tests/test_phase9_auth_hardening.py` keeps auth rate-limit behavior; `apps/api/tests/test_phase10_audit_privacy_exports.py` covers export expiry behavior | 7F-A tests exist. No Redis backend tests and no cleanup tests exist yet. |

---

## 3. Real 7F gaps

| # | Gap | Evidence | Real impact | In 7F scope? | Follow-up? | Expected test |
|---|---|---|---|---|---|---|
| G7F-1 | Rate limit is in-memory per process | `rate_limit_service.py:28-30` | With >1 worker each process has its own counters → effective limit = N×configured. Counters also reset on restart. | Yes (core) | — | Distributed backend enforces a single shared ceiling across simulated workers. |
| G7F-2 | Multi-worker can bypass the cap | `docker-compose.prod.yml` api `--workers 1` today; any scale-out breaks the limit silently | Abuse mitigation (G-01) and brute-force protection (G-13) silently weaken when prod scales. | Yes | — | With shared backend, two limiter instances sharing one store still 429 at the global cap. |
| G7F-3 | No Redis client/config in code | no `redis` import; `config.py` has no Redis getter | Cannot enable distributed limiting; dev compose `REDIS_URL` is dead config. | Yes, 7F-B | — | Config factory selects backend from env; absent Redis → memory. |
| G7F-4 | Redis outage policy still undecided/unimplemented | 7F-A kept only `InMemoryRateLimiter`; no Redis path exists yet | Operators still need an explicit behavior when Redis is down before 7F-B changes request paths. | Yes, decision blocks 7F-B | — | Outage tests prove chosen policy. |
| G7F-5 | No cleanup for expired `RevokedToken` | `models.py:448` field exists; no deleter anywhere | `revoked_tokens` grows unbounded; every authenticated request does `db.get(RevokedToken, jti)` (`deps.py:36`) — index keeps it O(1), but the table never shrinks. | Yes | — | Cleanup deletes rows with `expires_at < now`; keeps unexpired rows. |
| G7F-6 | No cleanup for expired `ExportJob` / files | `export_service.py:105` sets `expires_at`; no deleter; no file unlink | Disk fills with `<job.id>.jsonl`; `export_jobs` rows accumulate. | Yes | — | Cleanup removes/marks expired jobs and unlinks the file only when safe. |
| G7F-7 | No operational mechanism to run cleanup | `main.py` lifespan has no scheduler; no CLI/management command | Even if functions exist, there is no documented way to invoke them. | Yes (service + invocation surface + docs) | Scheduler/cron automation = deploy follow-up | Cleanup invokable headless (function/CLI) with a dry-run summary. |
| G7F-8 | No Redis/cleanup tests | `apps/api/tests/test_phase7f_rate_limit_service.py` covers 7F-A abstraction only | 7F-B and 7F-C still need targeted regression coverage. | Yes, 7F-B/7F-C | — | Section 11 matrix. |
| G7F-9 | Dev compose advertises Redis, prod does not provision it | `docker-compose.yml` vs `docker-compose.prod.yml` | Inconsistent infra story; "enable Redis in prod" is currently impossible without a compose change. | Partial: spec documents the gap; prod compose Redis service = deploy follow-up (no infra change this round) | Compose/deploy change deferred | N/A (doc + deploy decision). |

Semantic note for G7F-1/-2: the current API-key limiter is a **sliding
window** (`deque` of timestamps trimmed to a 60s cutoff). A Redis
`INCR`+`EXPIRE` fixed window is *not byte-identical* — at a window boundary a
client could in theory get up to ~2× the cap across two adjacent windows. This
is an accepted trade-off for operational simplicity and is called out as
pending decision #3.

---

## 4. Recommended scope decision

### Option A — minimal, safe 7F (recommended; now partially delivered)

- 7F-A has introduced a rate-limiter abstraction (interface + in-memory impl)
  that preserves the exact current contract and the `reset_all()` test seam.
- Add an **optional** Redis backend, selected only when `REDIS_URL` (or an
  explicit backend env) is configured. This remains 7F-B.
- Keep in-memory as the dev/test default; identical observable behavior when
  Redis is absent.
- Add idempotent, dry-run-capable cleanup services for `RevokedToken` and
  `ExportJob` (+ safe file unlink), invokable headless (function/CLI).
- Operational docs (env vars, local Redis, manual/cron cleanup, risks).
- Tests with a fake/stub Redis and SQLite; no real Redis required for the
  suite.
- **No migration. No scheduler inside the API process.**

### Option B — full operational 7F

- Redis required in production; add Redis to prod compose; in-app
  background worker/scheduler running cleanup automatically.
- Higher blast radius: changes prod infra, adds a long-lived task to the API
  process, couples availability to Redis.

### Option C — cleanup jobs only

- Implement only `RevokedToken`/`ExportJob` cleanup; do not touch
  rate-limit/Redis at all.

### Recommendation: **Option A**

Rationale:

- **Smallest blast radius.** 7F-A proved the split without migration, prod
  infra change, in-process scheduler, or contract change. 7F-B/7F-C should
  keep that discipline; each piece remains independently revertible.
- **Dev/test parity.** In-memory remains the default; the existing
  `test_phase9` suite (including `reset_all`) keeps passing unchanged.
- **Security-adjacent path stays observable-equivalent.** The 429 +
  `Retry-After` contract on `deps.py` and `routes_auth.py` is preserved.
- Redis-mandatory-in-production and prod-compose Redis provisioning are
  recorded as **deploy/follow-up decisions** (pending decision #1, gap
  G7F-9), not implemented in this round.
- In-app scheduler is explicitly *out* of Option A; automated scheduling is a
  deploy concern (external cron / platform scheduler), recorded as follow-up.

---

## 5. Distributed rate limit — spec

### API / abstraction

Proposed module: `apps/api/app/domain/services/rate_limit_service.py`
(**extend the existing module in place**, do not relocate — `deps.py:7` and
`routes_auth.py:20` import from it, and `test_phase9` imports `reset_all`
from it; relocating would break public-ish import paths and tests).

Shape (illustrative, not prescriptive — implementation prompt finalizes):

- A `RateLimiterBackend` protocol/interface with two operations mirroring
  today's functions:
  - `hit_api_key(key_id: str, per_minute: int) -> int | None`
    (returns `Retry-After` seconds or `None`).
  - login-failure trio equivalent (`check` / `record` / `reset`).
- `InMemoryRateLimiter` — the current `deque`/`Lock` logic, moved behind the
  interface unchanged.
- `RedisRateLimiter` — fixed-window counter via `INCR` + `EXPIRE`.
- A module-level factory that resolves the active backend once from config.
- The existing free functions (`check_api_key_rate_limit`,
  `check_login_rate_limit`, `record_login_failure`, `reset_login_failures`,
  `reset_all`) **remain as the public surface**, delegating to the active
  backend. Call sites in `deps.py` and `routes_auth.py` do not change.
- `reset_all()` must still work for tests: in-memory clears dicts; Redis impl
  deletes only keys under the test prefix (or is a no-op + tests use the
  in-memory backend — see Section 11).

Responsibilities: enforce per-`ApiKey.id` and per-`email|ip` ceilings;
preserve the 429/`Retry-After`/`detail` contract; work with Redis when
configured; fall back to in-memory otherwise; be testable without a real
Redis.

### Redis config (proposed env, following `config.py` lazy-getter convention)

- `REDIS_URL` — e.g. `redis://host:6379/0`. Already present in dev compose.
- `EVALOPS_RATE_LIMIT_BACKEND` = `memory` | `redis` | `auto` (default
  `auto`: `redis` iff `REDIS_URL` set and reachable at first use, else
  `memory`).
- `EVALOPS_REDIS_TIMEOUT_MS` — short connect/op timeout (proposed default
  ~100–250ms) so a slow Redis cannot stall the request path.
- Key prefix: `evalops:rl:` (e.g. `evalops:rl:apikey:<key_id>:<window>` and
  `evalops:rl:login:<sha256(email|ip)>:<window>`).

Decisions encoded here (recommendation; final answer in Section 13):

- **Dev/test, Redis unset → memory.** Behavior identical to today.
- **Production, Redis unset →** log a *warning* at startup (not a hard error)
  in Option A, so a misconfigured deploy degrades to single-worker semantics
  instead of failing to boot. Hard-fail is pending decision #1.
- **Redis outage at request time →** recommended split policy:
  - API-key limiter (`deps.py`): **fail-open** with a logged warning. Rate
    limiting is abuse *mitigation*, not an auth boundary; auth
    (`verify_api_key`, expiry, scopes) still fully enforced. Availability is
    preferred over hard-blocking legitimate ingest on a Redis blip.
  - Login-failure limiter (`routes_auth.py`): **fall back to the in-memory
    limiter** for the duration of the outage rather than fail-open, because
    this one is brute-force protection. Degraded (per-process) but still
    enforcing *something*.
  - This split is a recommendation; pending decision #2 may collapse it to a
    single uniform policy.

### Rate-limit semantics

- **Fixed window per minute** via `INCR` + `EXPIRE(window)` keyed by
  `ApiKey.id`. Chosen for equivalence-of-intent with the current 60s cap and
  for atomicity/simplicity. Documented trade-off vs the current sliding
  window: up to ~2× burst possible across a window boundary (gap G7F-9 note;
  pending decision #3 if stricter behavior is required → sliding window via
  sorted set / Lua).
- Granularity: per `ApiKey.id` (already the case — **never the raw key**).
  Login: per `sha256(email|ip)` (do not store raw email in the key).
- TTL: window length (60s API-key, 300s login) via `EXPIRE`; keys self-expire,
  no cleanup job needed for rate-limit keys.
- Behavior at limit: unchanged — HTTP 429, `Retry-After` header,
  `detail="too_many_requests"` (API key) / `"too_many_attempts"` (login).
- Headers: **no new headers** in this phase. Current code emits only
  `Retry-After` on 429; do not introduce `X-RateLimit-*` now (would be a
  contract addition; out of scope).
- Secret hygiene: never put the raw `X-EvalOps-Key` value in a Redis key or
  value. Use `ApiKey.id` (already the limiter key). Never store the secret or
  its hash in Redis. Login key uses a salted/plain hash of `email|ip`, not the
  raw email.

### Tests (rate limit)

- Memory backend (default) preserves current behavior — existing
  `test_phase9` cases pass unchanged.
- Redis backend (fake/stub): `INCR` increments, key `EXPIRE`s, count resets
  after window.
- Limit enforced per key; buckets independent across keys (parity with
  `test_phase9:132`).
- Two limiter instances sharing one fake store both observe the shared count
  (simulates multi-worker — proves G7F-1/-2 closed).
- Expired/revoked key never reaches the limiter (auth rejects first in
  `deps.py:72-76` before `:82`) — assert no Redis hit recorded.
- Redis outage follows the chosen policy (fail-open API-key / in-memory
  fallback login).
- Redis key never equals/contains the raw API key or raw email.

---

## 6. Cleanup jobs — spec

### Targets

1. **Expired `RevokedToken`** — delete rows where `expires_at < now`.
   - Keep rows whose `expires_at >= now` (still actively denying a live JWT).
   - Safe because once `expires_at` passes, the JWT itself is expired and
     `decode_access_token` (`deps.py:30`) rejects it regardless; the denylist
     row is redundant.
2. **Expired `ExportJob`** — handle jobs where `expires_at < now`.
   - Remove the on-disk file `<job.id>.jsonl` under `exports_dir()` if present
     and safe to delete.
   - Decide row disposition: hard-delete vs mark (see pending decision #5).
     Recommended default: **hard-delete the row and unlink the file**, because
     download already returns 410 for expired jobs (`routes_phase6.py:106-113`)
     so an expired job has no remaining product value; audit of the *creation*
     is independent (`audit_logs`, written at `export_service.py:108`) and is
     **not** touched by cleanup.
   - Keep non-expired jobs and their files untouched.
   - Do not break audit/privacy: cleanup must never delete `audit_logs` rows.

(State verified in models before deciding: `RevokedToken.expires_at`
non-nullable indexed `models.py:448`; `ExportJob.expires_at` nullable
`models.py:360` — cleanup must treat `expires_at IS NULL` as "no expiry, skip",
not "expired".)

### Invocation surface — decision

Options: in-process startup task / in-app infinite scheduler / admin endpoint
/ CLI command / external cron / separate job.

Recommended (Option A):

- Implement **idempotent, testable service functions first**
  (`cleanup_revoked_tokens(db, *, now=None, dry_run=False) -> CleanupSummary`,
  `cleanup_export_jobs(db, *, now=None, dry_run=False) -> CleanupSummary`).
- Expose a **CLI / module entrypoint** (e.g.
  `python -m app.maintenance.cleanup [--dry-run]`) following the existing
  "plain function + thin shell" convention. No new HTTP contract.
- **Do not** start an infinite scheduler inside the API process in this phase
  (would add a long-lived task to `main.py` lifespan — explicit decision, not
  incremental; pending decision #4).
- Document external cron / platform scheduler invoking the CLI as the
  recommended operational pattern (deploy follow-up, not code this round).

### Per-cleanup contract

For each cleanup function:

- **Inputs:** `db: Session`, injectable `now` (for tests), `dry_run: bool`,
  optionally a `batch_size` / `limit` to bound a single run.
- **Removal criteria:** `expires_at IS NOT NULL AND expires_at < now`.
  `RevokedToken`: delete row. `ExportJob`: unlink file (if safe) then
  delete/mark row per decision #5.
- **Transaction:** one transaction per batch; `dry_run` performs the SELECT
  and returns counts but commits nothing and unlinks nothing.
- **Return/summary:** `CleanupSummary` with counts (`scanned`, `deleted`,
  `files_removed`, `skipped_unsafe`, `dry_run`). Returned and logged.
- **Safe logs:** log counts and job ids, **never** absolute file paths or
  token `jti` values verbatim if considered sensitive (job id is a generated
  opaque id, safe to log; do not log `revoked_tokens.jti`).
- **Tests:** Section 11.

### File-deletion safety (ExportJob)

- Resolve the deletion target as `exports_dir() / f"{job.id}.jsonl"` —
  reconstruct from the (validated) job id, do **not** trust
  `ExportJob.file_path` blindly for the unlink path.
- Before unlinking: `resolve()` the path and assert it is **inside**
  `exports_dir().resolve()` (reject path traversal / `..`).
- Do **not** follow symlinks — refuse to unlink if the target is a symlink
  (`path.is_symlink()`), count as `skipped_unsafe`.
- Never delete outside `exports_dir()`.
- Idempotent: a missing file is success (already gone), not an error.

---

## 7. Configuration and deploy

Proposed env (documentation; implemented in the implementation phase):

| Env | Default | Effect |
|---|---|---|
| `REDIS_URL` | unset | Redis DSN. Already in dev compose; absent in prod compose today. |
| `EVALOPS_RATE_LIMIT_BACKEND` | `auto` | `memory` \| `redis` \| `auto`. |
| `EVALOPS_REDIS_TIMEOUT_MS` | ~100–250 | Short Redis op timeout (request-path safety). |

Behavior by environment:

- **dev/test:** no `REDIS_URL` → `memory`. Existing suite unaffected.
- **dev compose:** `REDIS_URL` already set; with `backend=auto` the app would
  use the existing `redis:7-alpine` service once code reads it.
- **prod:** `docker-compose.prod.yml` has **no** redis service and runs
  `--workers 1`. To actually run distributed limiting in prod, a Redis service
  + `REDIS_URL` must be added to the prod deploy — recorded as **deploy
  follow-up / pending decision #1** (no infra file change this round).

Validate Redis locally (documentation, not run now):

- `docker compose up redis` then `redis-cli -u redis://localhost:6379/0 ping`.

Run cleanup (documentation, not run now):

- Manual: `python -m app.maintenance.cleanup --dry-run` then without
  `--dry-run`.
- Recommended automation: external cron / platform scheduler invoking the CLI
  (deploy follow-up).

No deploy implementation is performed in 7F spec or its first implementation
slice beyond the optional Redis client wiring; prod-compose Redis is a separate
infra change.

---

## 8. Out of scope

- Frontend (`apps/web`).
- SDK (`packages/sdk-python`).
- Migrations / new Alembic revisions — unless a critically missing field is
  discovered (none is: both expiry fields exist).
- 7B refactor (service extraction, `_project_or_404` dedup, router thinning).
- Plan / billing / quota schema changes.
- WebSocket / realtime.
- New OpenTelemetry / Prometheus metrics.
- Auth replacement / JWT format change / refresh-token rotation.
- Real production rollout / actually scaling workers.
- Deleting real data without dry-run + tests.
- New rate-limit response headers (`X-RateLimit-*`).
- In-app infinite scheduler (Option B territory; pending decision #4).
- Adding Redis to `docker-compose.prod.yml` (deploy follow-up; pending
  decision #1).

---

## 9. Proposed architecture

- `rate_limit_service.py` (already extended in place by 7F-A):
  - `RateLimiterBackend` interface (protocol).
  - `RateLimitResult` value object.
  - `InMemoryRateLimiter` — today's `deque`/`Lock` logic, behind the interface.
  - existing free functions kept as the stable facade (delegating).
- 7F-B extension in the same module:
  - `RedisRateLimiter` — fixed-window `INCR`/`EXPIRE`.
  - backend factory resolving from config once.
- New config getters in `apps/api/app/config.py` (`redis_url()`,
  `rate_limit_backend()`, `redis_timeout_ms()`), same lazy `os.environ`
  pattern as `max_body_bytes()`.
- New `apps/api/app/maintenance/cleanup.py` (or
  `apps/api/app/domain/services/cleanup_service.py`):
  - `cleanup_revoked_tokens(...)`, `cleanup_export_jobs(...)`,
    `CleanupSummary`.
  - thin `__main__` / `python -m` entrypoint.
- Integration touch points:
  - `deps.get_project_from_api_key` — **no signature/behavior change**; still
    calls `check_api_key_rate_limit(selected.id, …)` which now delegates.
  - `routes_auth.login` — unchanged call sites.
  - No change to `main.py` lifespan in Option A.
- No public contract change (endpoints, headers, status codes, schemas).
- Safe structured logs only (counts/ids, no paths/secrets).
- Isolated tests with fake Redis + SQLite.

Proposed new files:

| Path | Responsibility | Called by | Risks |
|---|---|---|---|
| `apps/api/app/maintenance/__init__.py` | package marker | — | none |
| `apps/api/app/maintenance/cleanup.py` | cleanup services + CLI entrypoint | operator (CLI), tests, optionally external cron | data deletion → must be idempotent + dry-run + path-safe |
| (already extended) `apps/api/app/domain/services/rate_limit_service.py` | 7F-A backend abstraction + future Redis impl | `deps.py`, `routes_auth.py`, tests | security-adjacent path; outage policy must be correct before 7F-B |
| (extended) `apps/api/app/config.py` | Redis/backend env getters | rate-limit factory | misconfig → wrong backend; covered by `auto` default |

---

## 10. Future implementation plan (subphases)

### 7F-A — Rate-limit abstraction + in-memory backend

Status: **done / integrated** in PR #8 (`63da5af`), implementation commit
`abb331b refactor(evalops): abstract api rate limiter`.

- Introduced `RateLimiterBackend`, `RateLimitResult`, and
  `InMemoryRateLimiter`.
- Kept the free-function facade:
  `check_api_key_rate_limit`, `check_login_rate_limit`,
  `record_login_failure`, `reset_login_failures`, `reset_all`.
- Preserved current in-memory sliding window/deque/`Lock` behavior.
- Kept raw API keys out of limiter keys through `api_key_rate_limit_key()`.
- Added `apps/api/tests/test_phase7f_rate_limit_service.py`.
- Did not add Redis, a Redis dependency, cleanup jobs, migrations, frontend,
  or SDK changes.

### 7F-B — Optional Redis backend

- **Next recommended implementation step.**
- Decide Redis outage policy before coding this subphase. Initial
  recommendation: API-key limiter fail-open with warning/safe log to preserve
  ingest availability; login limiter falls back to in-memory to retain some
  brute-force protection. Product/ops may choose another policy, but it must
  be explicit before 7F-B.
- Add Redis client dep + `RedisRateLimiter` (fixed window); config factory;
  outage policy (per decision #2).
- Likely files: `rate_limit_service.py`, `config.py`, `pyproject.toml`
  (add `redis` dependency), new tests with fake/stub Redis.
- Acceptance: shared-store test proves multi-worker cap; outage test proves
  chosen policy; no raw key/email in Redis keys; memory default unchanged.
- Risk: medium (security-adjacent). Revert = `backend=memory` + drop impl.

### 7F-C — Cleanup services

- `cleanup_revoked_tokens`, `cleanup_export_jobs`, `CleanupSummary`, dry-run,
  path-safe unlink, CLI entrypoint.
- Likely files: `apps/api/app/maintenance/cleanup.py` (new),
  `tests/test_phase7f_cleanup.py` (new).
- Acceptance: Section 11 cleanup matrix green; dry-run mutates nothing;
  idempotent; path-traversal/symlink refused.
- Risk: medium (deletes data/files). Revert = remove module; no schema impact.

### 7F-D — Ops docs

- Update `docs/ops/` with: Redis env vars, local Redis validation, manual/cron
  cleanup, outage policy, risks. Possibly a new
  `docs/ops/rate-limit-and-cleanup.md`.
- Acceptance: docs reviewed; matches shipped behavior.
- Risk: none (docs only).

Recommended order from current `main`: 7F-B → 7F-C → 7F-D.

---

## 11. Mandatory future tests

### Rate limit

- Memory backend keeps current behavior (`test_phase7f_rate_limit_service.py`
  and existing `test_phase9` coverage).
- Redis backend: `INCR` increments; key `EXPIRE`s; count resets next window.
- Per-key enforcement; independent buckets across keys.
- Shared-store / two-instance test → global cap holds (multi-worker proof).
- Raw API key / raw email never present in any Redis key or value.
- Outage policy: API-key fail-open (logged) / login in-memory fallback
  (per final decision #2).
- Revoked/expired key rejected by auth before limiter is consulted (no Redis
  hit recorded).
- No auth/ingest regression: `test_phase9`, `test_phase2_tracing`,
  `test_phase7e_api_key_expiry` still green.

### Cleanup

- Expired `RevokedToken` deleted; non-expired preserved;
  `expires_at IS NULL` skipped.
- Expired `ExportJob` removed/marked per decision #5; non-expired preserved.
- Associated file unlinked only when inside `exports_dir()` and not a symlink.
- Path traversal / symlink target → `skipped_unsafe`, not deleted.
- `dry_run=True` changes no rows and unlinks no files; returns accurate
  counts.
- Idempotent: second run is a no-op with zero deletions.
- `audit_logs` rows untouched by either cleanup.

### Validation discipline

- Targeted: `pytest apps/api/tests/test_phase7f_*.py -q`.
- Auth/quota regression: `pytest apps/api/tests -q -k "rate_limit or auth or
  export or phase9 or phase7e"`.
- Contract: full `pytest apps/api/tests -q`.
- Tests must not require a real Redis (use a fake/in-proc stub). If a real
  Redis smoke is ever run, use a disposable container (mirroring the 7A
  disposable-Postgres discipline in `docs/ops/database-migrations.md`).

---

## 12. 7F acceptance criteria

7F is complete only when:

- Redis/fallback/outage policy is explicitly decided and documented.
- Distributed rate limiting (7F-A abstraction already done + 7F-B optional
  Redis backend) is implemented per approved scope, with the
  429/`Retry-After`/`detail` contract preserved.
- Cleanup functions for `RevokedToken` and `ExportJob` (+ safe file unlink)
  are implemented, idempotent, dry-run-capable, and tested per approved scope.
- dev/test still works with no Redis (existing suite green unchanged).
- Production has a clear, documented instruction for enabling Redis (even if
  the prod-compose change itself is a tracked deploy follow-up).
- All targeted + regression + contract tests pass.
- Operational docs updated.
- Documentary code review approved before implementation; implementation code
  review approved after.
- No regression in 7E / 7D / 7C behavior.

---

## 13. Pending decisions for the user

| # | Question | Recommendation |
|---|---|---|
| 1 | Redis mandatory in production, or optional-with-warning? | **Optional-with-startup-warning** for Option A (degrade to single-worker rather than fail boot). Mark "Redis required + provisioned in prod compose" as a tracked **deploy follow-up**. |
| 2 | On Redis outage: fail-open or fail-closed? | **Split:** API-key limiter **fail-open** (logged) — abuse mitigation, auth still enforced; login limiter **fall back to in-memory** — preserve brute-force protection. Acceptable alternative: uniform fail-open if a single policy is required. |
| 3 | Fixed window, sliding window, or token bucket? | **Fixed window** (`INCR`+`EXPIRE`) for equivalence-of-intent and atomic simplicity; accept the documented ~2× boundary burst. Revisit to sliding window only if abuse data demands it. |
| 4 | Cleanup via manual/CLI/external cron, or in-app background? | **Service functions + CLI entrypoint**, driven by external cron/platform scheduler. **No infinite in-app scheduler** in this phase. |
| 5 | Expired `ExportJob`: hard-delete, mark, or both? | **Hard-delete row + unlink file** (download already 410s expired jobs; creation audit is independent and untouched). Choose "mark" only if a retention/audit requirement on the job row itself is stated. |
| 6 | May `RevokedToken` cleanup hard-delete expired rows with no extra retention? | **Yes.** After `expires_at` the underlying JWT is already expired and independently rejected; the denylist row is redundant. |
| 7 | Must dev/test keep working without Redis? | **Yes.** In-memory default; no real Redis in the suite. |
| 8 | One PR or split 7F-A/B/C(/D)? | **Split confirmed.** 7F-A is merged; continue with B → C → D. B is security-adjacent; C deletes data; D is docs. Smaller reviews, granular revert. |

---

## 14. Recommended next prompt

This spec has two decisions that are genuinely blocking, but **only for the
remaining subphases that encode them**:

- **Decision #2 (Redis outage policy)** blocks **7F-B (Redis backend)** because
  it changes security/availability behavior on request paths.
- **Decision #5 (ExportJob disposition)** blocks **7F-C (cleanup)** because it
  changes data retention and deletion behavior.

Decisions #1 and #4 affect deploy/ops scope but do not block the already-merged
7F-A. Recommended path:

1. Before starting **7F-B**, user confirms decision #2 (and ideally #1/#3/#8).
2. Before starting **7F-C**, user confirms decision #5 (and ideally #4/#6).
3. Then run the implementation prompt for **7F-B only**:

> Você está no EvalOps em `main`, após review documental de
> `docs/plans/evalops-phase7f-redis-cleanup-spec.md`, e após a política de
> outage Redis ser decidida. Implemente **somente 7F-B**: backend Redis
> opcional para o rate limiter existente, preservando o facade público
> (`check_api_key_rate_limit`, `check_login_rate_limit`,
> `record_login_failure`, `reset_login_failures`, `reset_all`) e o contrato
> 429/`Retry-After`/`detail`. Não implementar cleanup jobs. Sem migration. Não
> tocar frontend/SDK. Testes devem provar limite compartilhado, política de
> outage escolhida, ausência de raw API key/email em chaves Redis e default
> in-memory quando Redis não estiver configurado. Entregar pronto para code
> review.

4. After 7F-B merges: 7F-C (cleanup, encodes #4/#5/#6), then 7F-D (ops docs).

If the user declines to decide #2/#5 now, do **not** start 7F-B or 7F-C until
the relevant decision is made.
