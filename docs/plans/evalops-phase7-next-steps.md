# EvalOps Phase 7 next steps

Date: 2026-05-19
Base branch: `main`
Base HEAD: `935c3dc`
Original next-steps snapshot: `0ab562e`; previous documentation baseline: `b4ffed2`.
Primary status source: `docs/audits/evalops-phase7-status-after-7bc.md`

This roadmap reflects current `main` after PR #11 merged the 7F-D cleanup CLI
operationalization and after the basic Oracle VM rollout was applied on
2026-05-19. The old prompts for frontend polling, 7F-A, 7F-B, 7F-C,
docs-only 7F-D, and initial deploy validation are historical.

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
| 7F-D ops maintenance / Oracle VM rollout | done | Monitor the installed cleanup cron/log and Redis-backed API runtime; formalize deploy only if needed. |

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

- PR #11 merge: `935c3dc Merge pull request #11 from rouggerxavier/phase-7f-d-ops-maintenance`.
- Commit: `2980396 feat(evalops): operationalize cleanup maintenance CLI`.
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

Oracle VM basic rollout (applied):

- Rollout record: `docs/audits/evalops-oracle-vm-rollout-2026-05-19.md`.
- VM repo reached clean `main...origin/main` at `935c3dc`.
- EvalOps remains a manual Docker deployment using SQLite on the VM.
- Redis runs as `evalops-redis` on Docker network `evalops-runtime`, with no
  host port published.
- `evalops-api` reported `RedisRateLimiter`.
- Cleanup dry-run/apply returned `ok: true` with zero scanned rows in the
  observed rollout.
- Cleanup script and cron were installed; expected cron is 03:15 to avoid the
  existing DocOps backup at 03:00.
- DocOps was observed on the same VM and was not changed.

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

### 1. Operational monitoring after Oracle VM rollout

Objective: confirm the applied VM rollout remains healthy without changing
product code.

- Check `/var/log/evalops-cleanup.log` after the first 03:15 scheduled run.
- Confirm `evalops-api` and `evalops-redis` remain `Up`.
- Confirm the active rate-limit backend still reports `RedisRateLimiter`.
- Confirm `/docs` still returns `HTTP 200 OK` through the VM port mapping.
- Optionally remove the old `evalops-api-prev-*` rollback container after a
  stable observation period, if it still exists.

### 2. 7B follow-up only when opportunistic

Objective: reduce remaining `_project_or_404` wrappers and router coupling only
when touching related code for real changes.

### 3. Explicitly deferred follow-ups

- Formalize the current manual Docker VM deployment in a production deploy
  definition only if operations need it.
- Add EvalOps SQLite backups before relying on the VM for real persisted data.
- Keep Docker Compose out of the VM runtime unless a separate deploy change
  intentionally moves the service away from the current manual container model.

## Global Phase 7 Close Checklist

Blocking for full Phase 7 close:

- [x] 7A: Alembic path validated with disposable Postgres smoke.
- [x] 7B: ownership/service follow-up remains partial and is explicitly accepted as opportunistic debt.
- [x] 7C: structured request logging/request ID implemented.
- [x] 7D: SDK retry/dead-letter/replay implemented.
- [x] 7E-backend: `ApiKey.expires_at` merged (PR #6).
- [x] 7E-frontend: traces auto-refresh polling merged (PR #7).
- [x] 7F-A: rate limiter abstraction merged (PR #8).
- [x] 7F-B: Redis/distributed backend implemented (PR #9).
- [x] 7F-C: cleanup jobs implemented (PR #10).
- [x] 7F-D: cleanup CLI operationalization implemented, docs updated, and basic Oracle VM rollout applied.

Verification commands/checks:

- `git status --short`
- for future migrations only: `cd apps/api && alembic upgrade head` on disposable DB
- `rg -n "_project_or_404" apps/api/app`
- 7F-B targeted: `cd apps/api && .venv/bin/python -m pytest tests/test_phase7f_redis_rate_limit.py -q --tb=short -p no:warnings`
- 7F-C targeted: `cd apps/api && .venv/bin/python -m pytest tests/test_phase7f_cleanup_jobs.py -q --tb=short -p no:warnings`
- 7F-D targeted: `cd apps/api && .venv/bin/python -m pytest tests/test_phase7f_cleanup_cli.py -q --tb=short -p no:warnings`

## Next Prompt

```text
Você está no EvalOps em main após o rollout básico da Fase 7F na Oracle VM.
Próximo passo padrão: monitorar operação sem mudar produto.

Objetivo:
- checar `/var/log/evalops-cleanup.log` depois da primeira execução agendada;
- confirmar `evalops-api` e `evalops-redis` Up;
- confirmar backend `RedisRateLimiter`;
- avaliar remoção do container antigo de rollback após estabilidade;
- planejar backup do SQLite se houver dados reais.

Restrições:
- não adicionar scheduler dentro da API;
- não alterar schema/migrations;
- não migrar a VM para Docker Compose/Postgres sem decisão separada;
- não tocar DocOps.
```
