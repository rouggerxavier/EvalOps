# EvalOps Phase 7 next steps

Date: 2026-05-17
Base branch: `main`
Base HEAD: `f13f24c`
Primary status source: `docs/audits/evalops-phase7-status-after-7bc.md`

This is the operational roadmap from the current `main`, after 7B/7C and the
Fix-7B work were merged. It supersedes the old linear plan where all of 7D-7F
were treated as untouched.

## Current Status Summary

| Subphase | Status | Next step |
|---|---|---|
| 7A Alembic/migrations | partial | Verify Postgres smoke and record result. |
| 7B service extraction/ownership | partial | Leave as follow-up unless touching phase 5 routers; remaining `_project_or_404` wrappers are real. |
| 7C structured logging/request_id | done | Do not reimplement. Monitor in deploy/runtime validation. |
| 7D SDK retry/dead-letter | partial | Implement only dead-letter/replay gap if still in Phase 7. |
| 7E `ApiKey.expires_at`/polling | pending | Decide backend key expiry vs UX polling split. |
| 7F Redis/cleanup jobs | pending / post-MVP candidate | Implement when multi-worker or retention pressure exists. |

## Recommended Order

### 1. Verify 7A on Postgres

Objective: prove the existing Alembic setup is deploy-ready before adding new
migrations.

Likely files:

- `docs/ops/database-migrations.md`
- `docs/plans/baseline.md`
- `docker-compose.prod.yml`
- `apps/api/alembic/versions/0001_baseline_schema.py`

Risks:

- SQLite success does not prove Postgres readiness.
- Legacy DBs require `alembic stamp 0001_baseline`; running `upgrade head` on an
  already-created schema may fail.

Tests/commands:

- `cd apps/api && DATABASE_URL=<postgres-url> alembic upgrade head`
- `cd apps/api && DATABASE_URL=<postgres-url> alembic current`
- optional disposable rollback: `alembic downgrade base`

Acceptance:

- Empty Postgres reaches `0001_baseline`.
- Legacy stamping instructions remain correct.
- Docs record exactly what was run and any blocker.

Code review before commit: yes.

Suggested model/effort: GPT-5.5 high.

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

- Adding schema before 7A Postgres verification.
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

- [ ] Postgres Alembic smoke is verified or explicitly waived.
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
- `cd apps/api && alembic upgrade head` on disposable SQLite/Postgres
- `rg -n "_project_or_404" apps/api/app`
- `cd apps/api && .venv/bin/python -m pytest tests/test_phase13_logging_request_id.py -q --tb=short -p no:warnings`
- `cd packages/sdk-python && python -m pytest tests -q --tb=short`

## Next Prompt

Use this prompt next:

```text
Você está no EvalOps em main. Faça apenas verificação/documentação da 7A
Postgres Alembic readiness, sem implementar código produtivo.

Leia:
- AGENTS.md e CLAUDE.md se existirem;
- docs/ops/database-migrations.md;
- docs/plans/baseline.md;
- docs/audits/evalops-phase7-status-after-7bc.md;
- docker-compose.prod.yml;
- apps/api/alembic/versions/0001_baseline_schema.py.

Confirme branch/HEAD/status. Se houver Postgres/Docker disponível, rode smoke
em DB descartável: alembic upgrade head, alembic current e rollback opcional.
Se não houver, documente o bloqueio e o comando exato que deve ser rodado.

Atualize docs apenas com evidência. Não altere backend/frontend/SDK. Não faça
commit/push.
```
