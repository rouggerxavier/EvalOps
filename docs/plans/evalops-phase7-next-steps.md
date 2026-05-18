# EvalOps Phase 7 next steps

Date: 2026-05-18
Base branch: `main`
Base HEAD: `f44ed19`
Original next-steps snapshot: `0ab562e`; previous documentation baseline: `b4ffed2`.
Primary status source: `docs/audits/evalops-phase7-status-after-7bc.md`

This roadmap reflects current `main` after PR #7 merged `7E-frontend` polling.
The old prompt that asked to implement frontend polling is now historical.

## Current Status Summary

| Subphase | Status | Next step |
|---|---|---|
| 7A Alembic/migrations | done | Keep migration discipline: each new revision needs its own PR and disposable Postgres smoke. |
| 7B service extraction/ownership | partial / opportunistic follow-up | Touch only when changing Phase 5 routers; keep contract stable. |
| 7C structured logging/request_id | done | Do not reimplement; validate in deploy/runtime only if needed. |
| 7D SDK retry/dead-letter | done | Do not reimplement without a new concrete finding. |
| 7E-backend `ApiKey.expires_at` | done | Keep as shipped in PR #6 (`b4ffed2`) with migration `0002`. |
| 7E-frontend polling | done | Keep current bounded `router.refresh()` behavior; refine only via explicit follow-up if UX evidence appears. |
| 7F Redis/cleanup jobs | pending / operational follow-up | Preferred next candidate for multi-worker/readiness. Start from a spec first. |

## Evidence For 7E Completion

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

### 1. 7F Redis/cleanup spec first (default next step)

Objective: define operational behavior before implementation.

Spec should decide:

- Redis failure policy (`fail-closed`, `fail-open`, or explicit fallback policy).
- Cleanup retention policy for `RevokedToken` and `ExportJob` (+ file deletion grace window).
- Safety controls: idempotence, dry-run, observability, and rollback.

Do not implement 7F directly before this spec is reviewed.

### 2. Release notes / closure docs for 7E

Objective: close the 7E narrative cleanly after backend+frontend splits landed.

Deliverables:

- Short release note entry for PR #6 + PR #7 outcomes.
- Confirm 7E is complete in roadmap/baseline/audit docs.

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
- [ ] 7F: Redis/distributed rate limit + cleanup strategy implemented or formally deferred with trigger conditions.

Verification commands/checks:

- `git status --short`
- for future migrations only: `cd apps/api && alembic upgrade head` on disposable DB
- `rg -n "_project_or_404" apps/api/app`

## Next Prompt

```text
Você está no EvalOps em main. Próximo passo padrão: planejar somente 7F (spec),
sem implementar código ainda.

Objetivo do spec:
- definir Redis/distributed rate limit para multi-worker;
- definir cleanup de RevokedToken/ExportJob expirados (e arquivos de export) com
a política de retenção;
- definir política de falha Redis, idempotência, dry-run, métricas e rollback.

Restrições:
- não alterar backend/frontend/SDK/migrations nesta rodada;
- não fazer commit/push;
- preparar saída para code review documental.
```
