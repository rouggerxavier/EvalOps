# EvalOps Phase 7 next steps

Date: 2026-05-17
Base branch: `main`
Base HEAD: `0812b76`
Original next-steps snapshot: `0ab562e`; latest documentation verification:
`0812b76`.
Primary status source: `docs/audits/evalops-phase7-status-after-7bc.md`

This is the operational roadmap from the current `main`, after 7B/7C and the
Fix-7B work were merged. It supersedes the old linear plan where all of 7D-7F
were treated as untouched.

## Current Status Summary

| Subphase | Status | Next step |
|---|---|---|
| 7A Alembic/migrations | Postgres smoke approved on disposable DB | No longer blocking `0002+`; every new migration still needs its own PR and smoke. |
| 7B service extraction/ownership | partial | Leave as follow-up unless touching phase 5 routers; remaining `_project_or_404` wrappers are real. |
| 7C structured logging/request_id | done | Do not reimplement. Monitor in deploy/runtime validation. |
| 7D SDK retry/dead-letter | partial | Implement only dead-letter/replay gap if still in Phase 7. |
| 7E `ApiKey.expires_at`/polling | pending | Decide backend key expiry vs UX polling split. |
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
7D dead-letter/replay if SDK telemetry durability is the priority, or decide
and split 7E if credential expiry is the priority.

### 2. Finish Updated 7D Only If SDK Durability Is In Scope

Objective: add the missing dead-letter/replay layer without rewriting the retry
work from `40cf27a`.

Likely files:

- `packages/sdk-python/evalops/uploader.py`
- `packages/sdk-python/evalops/__init__.py`
- `packages/sdk-python/tests/test_sdk.py`
- `packages/sdk-python/README.md` if a public replay API is added

Risks:

- Regressing bounded `flush()`/`shutdown()`.
- Persisting sensitive payloads locally without a clear location/retention
  contract.
- Duplicating retry logic that already works.

Tests:

- Retry-exhausted transient failure writes dead-letter.
- Replay reads dead-letter and re-submits.
- Existing retry/drop tests still pass.
- Decision on permanent 4xx dead-letter behavior is explicit and covered.

Acceptance:

- Existing SDK API remains compatible.
- Dead-letter directory can be overridden with `EVALOPS_DEAD_LETTER_DIR`.
- Replay API is exported only if documented.

Code review before commit: yes.

Suggested model/effort: GPT-5.4/GPT-5.5 medium.

### 3. Decide And Split 7E

Objective: avoid coupling credential lifecycle and frontend polling in one PR.

Recommended split:

- 7E-backend: `ApiKey.expires_at` model/schema/API/auth enforcement.
- 7E-frontend: traces polling/auto-refresh, likely post-MVP.

Likely backend files:

- `apps/api/app/models.py`
- `apps/api/app/schemas.py`
- `apps/api/app/domain/services/api_key_service.py`
- `apps/api/app/deps.py`
- `apps/api/alembic/versions/0002_api_keys_expires_at.py`

Likely frontend files:

- `apps/web/app/o/[org]/p/[project]/traces/page.tsx`
- possible small client component under the traces route

Risks:

- Adding schema without a dedicated migration PR and smoke.
- Polling causing avoidable load or rate-limit noise.

Tests:

- Expired API key rejected.
- Future/no-expiry API key accepted.
- Past expiry rejected on creation/update if exposed.
- Frontend polling refreshes only when visible and can be paused, if kept.

Acceptance:

- Backend expiry can ship without polling.
- Polling is either implemented with guardrails or moved to follow-up.

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
- [ ] 7D is either completed with dead-letter/replay or formally narrowed to
      the retry/drop work in `40cf27a`.
- [ ] 7E and 7F are explicitly completed or moved to follow-up with rationale.

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
Você está no EvalOps em main. Próximo passo recomendado: implementar apenas a
lacuna 7D dead-letter/replay do SDK, preservando o retry/drop já entregue em
40cf27a. Confirme branch/HEAD/status, não reescreva retry, adicione testes
focados e não faça commit/push.
```

```text
Você está no EvalOps em main. Alternativa se credential expiry for prioridade:
decida e divida 7E em backend ApiKey.expires_at e frontend polling. A 7A
Postgres smoke já está validada, mas qualquer migration 0002+ precisa de PR
próprio e smoke próprio. Confirme branch/HEAD/status e não faça commit/push.
```
