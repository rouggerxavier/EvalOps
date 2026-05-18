# EvalOps Phase 7 next steps

Date: 2026-05-17
Base branch: `main`
Base HEAD: `b4ffed2`
Original next-steps snapshot: `0ab562e`; latest documentation verification:
`b4ffed2`.
Primary status source: `docs/audits/evalops-phase7-status-after-7bc.md`

This is the operational roadmap from the current `main`, after 7B/7C, 7D, and
the 7E-backend split were merged. It supersedes the old linear plan where all
of 7D-7F were treated as untouched.

## Current Status Summary

| Subphase | Status | Next step |
|---|---|---|
| 7A Alembic/migrations | Postgres smoke approved on disposable DB | No longer blocking `0002+`; every new migration still needs its own PR and smoke. |
| 7B service extraction/ownership | partial | Leave as follow-up unless touching phase 5 routers; remaining `_project_or_404` wrappers are real. |
| 7C structured logging/request_id | done | Do not reimplement. Monitor in deploy/runtime validation. |
| 7D SDK retry/dead-letter | done | PR #5 added dead-letter/replay after the earlier retry/drop work. Do not reimplement. |
| 7E-backend `ApiKey.expires_at` | done | PR #6 merged backend expiry, migration `0002_api_keys_expires_at`, generic 401 enforcement, and tests. |
| 7E-frontend polling | pending / follow-up | Implement only if live traces UX/demo value is the priority; keep polling bounded and pausable. |
| 7F Redis/cleanup jobs | pending / post-MVP candidate | Implement when multi-worker or retention pressure exists. |

## Recommended Order

### 1. 7A Postgres Smoke Is Validated

Objective: record that the existing Alembic setup was proven against disposable
Postgres before adding new migrations.

Recorded files:

- `docs/ops/database-migrations.md`
- `docs/plans/baseline.md`
- `docs/audits/evalops-phase7-status-after-7bc.md`
- `docs/plans/evalops-phase7-next-steps.md`

Risks:

- The completed smoke proves `0001_baseline` on an empty disposable Postgres;
  it does not prove production migration or legacy DB stamping.
- Legacy DBs require `alembic stamp 0001_baseline`; running `upgrade head` on an
  already-created schema may fail.
- Future schema changes still need their own revision, PR, and smoke.

Executed smoke:

- Disposable container `evalops-postgres-alembic-smoke` using
  `postgres:16-alpine`, DB `evalops_alembic_smoke`, port `55432`.
- `pg_isready` initially returned `no response`, then
  `/var/run/postgresql:5432 - accepting connections`.
- First Alembic attempt failed with `ModuleNotFoundError: No module named
  'psycopg'`; installing `psycopg[binary]>=3,<4` in the local API venv installed
  `psycopg` 3.3.4 and `psycopg-binary` 3.3.4.
- `alembic upgrade head` passed with `Running upgrade  -> 0001_baseline`.
- `alembic current` returned `0001_baseline (head)`.
- `alembic downgrade base` passed.
- A second `alembic upgrade head` passed and `current` again returned
  `0001_baseline (head)`.
- The disposable container was removed.

Acceptance:

- Empty Postgres reaches `0001_baseline`.
- Legacy stamping instructions remain correct.
- Docs record exactly what was run and any blocker.

Result: **7A Postgres smoke approved in a disposable DB**. The prior Docker/WSL
environment blocker is resolved. No production Postgres was used, and the
legacy `stamp` path was not tested.

Next: do not spend another pass on 7A unless a new migration is created. Choose
between 7E-frontend polling for live UX/demo value and 7F Redis/cleanup for
multi-worker or operational readiness.

### 2. 7D Is Complete Unless A New SDK Reliability Gap Is Found

Objective: keep the 7D status accurate after PR #5. The earlier retry/drop work
from `40cf27a` and the later dead-letter/replay implementation in `4ab910b`
cover the named 7D objective.

Likely files:

- `packages/sdk-python/evalops/uploader.py`
- `packages/sdk-python/evalops/__init__.py`
- `packages/sdk-python/tests/test_sdk.py`
- `packages/sdk-python/README.md` if a public replay API is added

Next step: do not schedule more 7D work as part of Phase 7 unless a fresh SDK
review finds a concrete regression or missing contract.

### 3. 7E Split Status After PR #6

Objective: record that backend credential expiry shipped separately, while
frontend polling remains a named follow-up.

Delivered backend evidence:

- PR #6 merged at `b4ffed2ded2cd01c78cdbd23ab710ea149aa8f7d`.
- `apps/api/alembic/versions/0002_api_keys_expires_at.py`.
- `ApiKey.expires_at` in model/schema/list/create responses.
- Expired API keys are rejected in `get_project_from_api_key` before scope,
  rate-limit, and `last_used_at` update.
- Expired keys return a generic 401.
- `apps/api/tests/test_phase7e_api_key_expiry.py`.

Frontend polling remains pending:

- `apps/web/app/o/[org]/p/[project]/traces/page.tsx`
- possible small client component under the traces route

Risks:

- Polling causing avoidable API traffic.
- Refreshing cursor-paged views in a way that confuses operators.
- Replacing the predictable manual refresh with a silent background behavior.

Tests for future polling:

- Polling refreshes only when visible and enabled.
- Manual refresh remains available.
- Cursor-paged views are skipped or intentionally handled.

Acceptance:

- Backend expiry stays done without requiring frontend polling.
- Polling is either implemented with guardrails or explicitly moved to
  follow-up/release notes.

Code review before commit: yes.

Suggested model/effort: GPT-5.3-Codex/GPT-5.4 medium.

Code review before commit: yes.

Suggested model/effort: GPT-5.4/GPT-5.5 medium.

### 4. 7B Follow-Up Opportunistically

Objective: complete the remaining ownership/service cleanup when it overlaps
with active bug or feature work.

Likely files:

- `apps/api/app/api/routes_phase5.py`
- `apps/api/app/ownership.py`
- phase 5 tests

Risks:

- Broad refactor with no behavior payoff.
- Accidental API contract changes.

Tests:

- phase 5 prompt/dataset/experiment tests;
- ownership denial and archived project cases if touched.

Acceptance:

- Remaining `_project_or_404` wrappers are removed or explicitly justified.
- No public contract changes.

Code review before commit: yes.

Suggested model/effort: GPT-5.4 high.

### 5. 7F As Operational Follow-Up

Objective: support distributed rate limiting and cleanup expired rows/files when
the deployment shape requires it.

Likely files:

- `apps/api/app/domain/services/rate_limit_service.py`
- `apps/api/scripts/cleanup.py` or equivalent
- `apps/api/pyproject.toml`
- `docker-compose*.yml`
- targeted backend tests

Risks:

- Redis outage policy affects availability/security.
- Cleanup can delete export files too aggressively.

Tests:

- memory backend regression;
- Redis backend with real Redis or fakeredis if accepted;
- cleanup dry-run;
- expired `RevokedToken` and `ExportJob` removed while valid rows remain.

Acceptance:

- Dev/test default remains memory.
- Redis is opt-in and documented.
- Cleanup is idempotent and safe to rerun.

Code review before commit: yes.

Suggested model/effort: GPT-5.5 high.

## Global Phase 7 Close Checklist

Blocking:

- [x] Postgres Alembic smoke is verified on disposable DB.
- [x] Structured request logging/request ID is implemented by `9e9a517`.
- [x] 7D SDK retry/dead-letter/replay is merged through PR #5.
- [x] 7E-backend `ApiKey.expires_at` is merged through PR #6.
- [ ] 7E-frontend polling is implemented or moved to follow-up with rationale.
- [ ] 7F is implemented or moved to follow-up with rationale.

Non-blocking but tracked:

- [ ] Remaining 7B wrappers in `routes_phase5.py` are removed or documented.
- [ ] Frontend polling decision is recorded.
- [ ] Redis/cleanup trigger conditions are recorded.

Recommended verification commands per area:

- `git status --short`
- for new migrations: `cd apps/api && alembic upgrade head` on disposable
  SQLite/Postgres
- `rg -n "_project_or_404" apps/api/app`
- `cd apps/api && .venv/bin/python -m pytest tests/test_phase13_logging_request_id.py -q --tb=short -p no:warnings`
- `cd packages/sdk-python && python -m pytest tests -q --tb=short`

## Next Prompt

Use one of these prompts next, depending on priority:

```text
Você está no EvalOps em main. Próximo passo se foco é produto/demo/UX:
implementar somente 7E-frontend polling/auto-refresh em traces. Preserve o
manual refresh, pause quando a aba estiver oculta, evite cursor pages por
padrão, não altere backend/SDK/migrations e não faça commit/push.
```

```text
Você está no EvalOps em main. Próximo passo se foco é produção/multi-worker:
implementar somente 7F Redis rate limit + cleanup jobs. Preserve o backend
in-memory como default dev/test, defina política de falha Redis, adicione
cleanup idempotente/dry-run e não faça commit/push.
```
