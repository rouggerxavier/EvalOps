# EvalOps Phase 7 next steps

Date: 2026-05-19
Base branch: `main`
Base HEAD: `5e785f0`
Original next-steps snapshot: `0ab562e`; previous documentation baseline: `b4ffed2`.
Primary status source: `docs/audits/evalops-phase7-status-after-7bc.md`

This roadmap reflects current `main` after PR #10 merged `7F-C` cleanup jobs,
the 7F-D docs commit (`5e785f0`), and the follow-up 7F-D operationalization of
the cleanup CLI contract. The old prompts for frontend polling, 7F-A, 7F-B,
7F-C, and docs-only 7F-D are historical.

## Current Status Summary

| Subphase | Status | Next step |
|---|---|---|
| 7A Alembic/migrations | done | Keep migration discipline: each new revision needs its own PR and disposable Postgres smoke. |
| 7B service extraction/ownership | partial / opportunistic follow-up | Touch only when changing Phase 5 routers; keep contract stable. |
| 7C structured logging/request_id | done | Do not reimplement; validate in deploy/runtime only if needed. |
| 7D SDK retry/dead-letter | done | Do not reimplement without a new concrete finding. |
| 7E-backend `ApiKey.expires_at` | done | Keep as shipped in PR #6 (`b4ffed2`) with migration `0002`. |
| 7E-frontend polling | done | Keep current bounded `router.refresh()` behavior; refine only via explicit follow-up if UX evidence appears. |
| 7F-A rate limiter abstraction | done | Keep as shipped in PR #8 (`63da5af`); do not redo the abstraction. |
| 7F-B Redis backend | done | Keep optional Redis behavior from PR #9 (`ba0978e`); enable in deploy only where shared buckets are needed. |
| 7F-C cleanup jobs | done | Keep dry-run-default cleanup service from PR #10 (`61592ff`); schedule externally, not in app lifespan. |
| 7F-D ops maintenance | implemented | Use the stable `python -m app.maintenance.cleanup` CLI contract for targets, limits, JSON output, exit codes, validation and external scheduler integration. |

## Evidence For 7E And 7F Completion

Backend split (already done):

- PR #6 merge: `b4ffed2ded2cd01c78cdbd23ab710ea149aa8f7d`.
- Commit: `2ff9070 feat(evalops): add api key expiration`.
- Migration: `apps/api/alembic/versions/0002_api_keys_expires_at.py`.

Frontend split (now done):

- Branch used: `phase-7e-frontend-polling`.
- Commit merged: `1b21b2b feat(web): add traces auto refresh`.
- Merge on `main`: `f44ed19 Merge pull request #7 from rouggerxavier/phase-7e-frontend-polling`.
- Files touched by implementation:
  - `apps/web/app/o/[org]/p/[project]/traces/page.tsx`
  - `apps/web/app/o/[org]/p/[project]/traces/traces-auto-refresh.tsx`
  - `apps/web/tests/security.test.mjs`
- Review/validation evidence carried in docs/history: `npm run test`, `npm run build`, and `npx tsc --noEmit` passed in the implementation review; final review had no P0/P1/P2; local artifact `apps/web/next-env.d.ts` was restored and stayed out of the merge commit.

7F-A rate limiter abstraction (now done):

- PR #8 merge: `63da5af Merge pull request #8 from rouggerxavier/phase-7f-a-rate-limit-abstraction`.
- Commit: `abb331b refactor(evalops): abstract api rate limiter`.
- Files touched by implementation:
  - `apps/api/app/domain/services/rate_limit_service.py`
  - `apps/api/tests/test_phase7f_rate_limit_service.py`
- Shipped surface:
  - `RateLimiterBackend`
  - `RateLimitResult`
  - `InMemoryRateLimiter`
  - public facade preserved: `check_api_key_rate_limit`,
    `check_login_rate_limit`, `record_login_failure`,
    `reset_login_failures`, `reset_all`
- Preserved behavior:
  - in-memory sliding window/deque/`Lock`;
  - API-key limiter keyed by safe `ApiKey.id`-derived key, not raw API key;
  - no Redis client/dependency;
  - no cleanup jobs;
  - no migration;
  - no frontend/SDK changes.

7F-B Redis backend (done):

- PR #9 merge: `ba0978e Merge pull request #9 from rouggerxavier/phase-7f-b-redis-rate-limit`.
- Commit: `1af8017 feat(evalops): add redis rate limit backend`.
- Files touched by implementation:
  - `apps/api/app/domain/services/rate_limit_service.py`
  - `apps/api/app/config.py`
  - `apps/api/pyproject.toml`
  - `apps/api/tests/test_phase7f_redis_rate_limit.py`
- Shipped behavior:
  - optional `RedisRateLimiter` selected by `EVALOPS_RATE_LIMIT_BACKEND` /
    `REDIS_URL`;
  - `memory` remains the default when Redis is not configured;
  - API-key limiter fails open on backend outage with safe warning;
  - login limiter falls back to local in-memory buckets during outage;
  - Redis keys avoid raw API keys and raw emails.

7F-C cleanup jobs (done):

- PR #10 merge: `61592ff Merge pull request #10 from rouggerxavier/phase-7f-c-cleanup-jobs`.
- Commit: `b3a3242 feat(evalops): add cleanup maintenance jobs`.
- Files touched by implementation:
  - `apps/api/app/maintenance/__init__.py`
  - `apps/api/app/maintenance/cleanup.py`
  - `apps/api/tests/test_phase7f_cleanup_jobs.py`
- Shipped behavior:
  - `python -m app.maintenance.cleanup` is dry-run by default;
  - `--apply` is required to delete rows/files;
  - expired `RevokedToken` rows are hard-deleted;
  - expired `ExportJob` rows use reconstructed `exports_dir()/<job.id>.jsonl`,
    not stored `file_path`, and refuse traversal/symlink targets;
  - missing files are idempotent; unsafe paths preserve rows.

7F-D cleanup CLI operationalization (implemented):

- Files touched by implementation:
  - `apps/api/app/maintenance/cleanup.py`
  - `apps/api/tests/test_phase7f_cleanup_cli.py`
  - `docs/ops/rate-limit-and-cleanup.md`
- Shipped behavior:
  - dry-run remains the default and `--apply` remains required for mutation;
  - `--target all|revoked-tokens|exports` selects the cleanup target;
  - `--limit N` bounds rows scanned per selected target;
  - `--json` emits one stable machine-readable object;
  - human output is a stable count summary;
  - exit code `0` means success with no cleanup errors, non-zero means invalid
    invocation or real cleanup failure.

## UX/Polling Review (UI UX Pro Max)

Scope reviewed: traces page polling UX only (`page.tsx`, `traces-auto-refresh.tsx`, source-level tests).

Verdict:

- The shipped behavior is coherent for MVP operations: manual refresh remains primary, auto-refresh is explicit and bounded.

Findings:

- High impact resolved: `router.refresh()` is real and no client-side duplicate fetch is introduced.
- High impact resolved: visibility guard (`document.hidden` + `visibilitychange`) pauses background churn.
- Medium impact resolved: cursor pagination guard pauses auto-refresh on paged views.
- Medium residual risk: every open visible tab still generates periodic reads; interval tuning may be needed by load profile.
- Low residual risk: this is polling, not realtime/WebSocket.

## Recommended Order

### 1. Deploy/operator validation for 7F

Objective: make the shipped 7F behavior real in the target environment without
changing product code.

- Configure `REDIS_URL` and `EVALOPS_RATE_LIMIT_BACKEND=redis` only where
  multi-worker/shared rate-limit buckets are needed.
- Keep `EVALOPS_RATE_LIMIT_BACKEND=memory` or unset Redis for local/single-worker
  environments where the current fallback is acceptable.
- Run cleanup dry-run first: `python -m app.maintenance.cleanup --json`.
- Schedule real cleanup externally:
  `python -m app.maintenance.cleanup --apply --json`.
- Do not add an in-app infinite scheduler.

### 2. 7B follow-up only when opportunistic

Objective: reduce remaining `_project_or_404` wrappers and router coupling only
when touching related code for real changes.

### 3. Explicitly deferred follow-ups

- Real production Redis provisioning is not done by this docs pass.
- Real cron/platform scheduler installation is not done by this docs pass.
- Production cleanup with `--apply` must be preceded by dry-run review in the
  target environment.

## Global Phase 7 Close Checklist

Blocking for full Phase 7 close:

- [x] 7A: Alembic path validated with disposable Postgres smoke.
- [ ] 7B: ownership/service follow-up resolved or explicitly accepted as debt.
- [x] 7C: structured request logging/request ID implemented.
- [x] 7D: SDK retry/dead-letter/replay implemented.
- [x] 7E-backend: `ApiKey.expires_at` merged (PR #6).
- [x] 7E-frontend: traces auto-refresh polling merged (PR #7).
- [x] 7F-A: rate limiter abstraction merged (PR #8).
- [x] 7F-B: Redis/distributed backend implemented (PR #9).
- [x] 7F-C: cleanup jobs implemented (PR #10).
- [x] 7F-D: cleanup CLI operationalization implemented and docs updated.

Verification commands/checks:

- `git status --short`
- for future migrations only: `cd apps/api && alembic upgrade head` on disposable DB
- `rg -n "_project_or_404" apps/api/app`
- 7F-B targeted: `cd apps/api && .venv/bin/python -m pytest tests/test_phase7f_redis_rate_limit.py -q --tb=short -p no:warnings`
- 7F-C targeted: `cd apps/api && .venv/bin/python -m pytest tests/test_phase7f_cleanup_jobs.py -q --tb=short -p no:warnings`
- 7F-D targeted: `cd apps/api && .venv/bin/python -m pytest tests/test_phase7f_cleanup_cli.py -q --tb=short -p no:warnings`

## Next Prompt

```text
Você está no EvalOps em main após 7F-A/7F-B/7F-C/7F-D. Próximo passo padrão:
validar operação/deploy sem mudar produto.

Objetivo:
- configurar Redis no ambiente alvo somente se multi-worker exigir buckets
  compartilhados;
- rodar `python -m app.maintenance.cleanup --json` em dry-run;
- instalar scheduler externo para `python -m app.maintenance.cleanup --apply --json`;
- registrar logs/resultados da primeira execução.

Restrições:
- não adicionar scheduler dentro da API;
- não alterar schema/migrations;
- não rodar cleanup `--apply` antes de revisar dry-run.
```
