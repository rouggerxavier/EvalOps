# EvalOps Phase 7 next steps

Date: 2026-05-18
Base branch: `main`
Base HEAD: `63da5af`
Original next-steps snapshot: `0ab562e`; previous documentation baseline: `b4ffed2`.
Primary status source: `docs/audits/evalops-phase7-status-after-7bc.md`

This roadmap reflects current `main` after PR #8 merged `7F-A` rate limiter
abstraction. The old prompt that asked to implement frontend polling, and the
later prompt that asked to implement 7F-A, are now historical.

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
| 7F-B Redis backend | pending | Preferred next candidate for multi-worker/readiness. Decide Redis outage policy first. |
| 7F-C cleanup jobs | pending | Do after 7F-B or when cleanup becomes priority; decide `ExportJob` disposition first. |
| 7F-D ops docs | pending / follow-up | Update final ops docs after 7F-B/7F-C behavior exists. |

## Evidence For 7E And 7F-A Completion

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

### 1. 7F-B Redis backend (default next step)

Objective: make the 7F-A abstraction useful for multi-worker/readiness by
adding an optional Redis backend.

Before coding 7F-B, decide:

- Redis outage policy (`fail-closed`, `fail-open`, or explicit fallback
  policy). Initial recommendation: fail-open with warning/safe log for API-key
  ingest availability; login limiter falls back to in-memory to retain some
  brute-force protection.
- Whether Redis is optional-with-warning or mandatory in production.
- Fixed window vs stricter sliding window/token bucket. Current spec
  recommends fixed window for 7F-B unless abuse data requires stricter
  behavior.

Do not redo 7F-A. Do not claim multi-worker rate limiting is solved until 7F-B
is implemented and validated.

### 2. 7F-C cleanup jobs

Objective: clean expired `RevokedToken` rows and expired `ExportJob` rows/files.

Before coding 7F-C, decide:

- Expired `ExportJob` disposition: hard-delete, mark, or both.
- Cleanup invocation surface: CLI/external cron vs in-app scheduler. Current
  spec recommends service functions + CLI entrypoint driven by external cron.
- Dry-run/idempotence/path-safety/audit expectations.

### 3. 7B follow-up only when opportunistic

Objective: reduce remaining `_project_or_404` wrappers and router coupling only when touching related code for real changes.

## Global Phase 7 Close Checklist

Blocking for full Phase 7 close:

- [x] 7A: Alembic path validated with disposable Postgres smoke.
- [ ] 7B: ownership/service follow-up resolved or explicitly accepted as debt.
- [x] 7C: structured request logging/request ID implemented.
- [x] 7D: SDK retry/dead-letter/replay implemented.
- [x] 7E-backend: `ApiKey.expires_at` merged (PR #6).
- [x] 7E-frontend: traces auto-refresh polling merged (PR #7).
- [x] 7F-A: rate limiter abstraction merged (PR #8).
- [ ] 7F-B: Redis/distributed backend implemented or formally deferred with trigger conditions.
- [ ] 7F-C: cleanup jobs implemented or formally deferred with trigger conditions.
- [ ] 7F-D: final ops docs updated after 7F-B/7F-C.

Verification commands/checks:

- `git status --short`
- for future migrations only: `cd apps/api && alembic upgrade head` on disposable DB
- `rg -n "_project_or_404" apps/api/app`

## Next Prompt

```text
Você está no EvalOps em main. Próximo passo padrão: 7F-B Redis backend, sem
reabrir 7F-A.

Antes de implementar, decidir explicitamente a política de outage Redis.
Recomendação inicial: API-key limiter fail-open com warning/log seguro para
preservar disponibilidade de ingest; login limiter fallback in-memory durante
outage para manter proteção parcial contra brute force.

Objetivo:
- adicionar backend Redis opcional ao rate limiter já abstraído em 7F-A;
- preservar facade pública e contrato 429/Retry-After/detail;
- provar limite compartilhado, política de outage e higiene de chaves Redis;
- manter default in-memory quando Redis não estiver configurado.

Restrições:
- não implementar cleanup jobs nesta rodada;
- não alterar frontend/SDK/migrations;
- não fazer commit/push;
- preparar saída para code review antes de commit.
```
