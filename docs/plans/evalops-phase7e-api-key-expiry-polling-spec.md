# EvalOps Phase 7E — ApiKey Expiration / Traces Polling Spec

Date: 2026-05-18
Branch inspected: `main`
HEAD inspected: `f44ed19`
Scope: historical spec + post-merge consolidation for 7E backend/frontend split.
No backend/frontend/SDK/schema/migration code changes were performed in this
documentation update.

Primary sources:

- `docs/plans/evalops-phase7-next-steps.md`
- `docs/audits/evalops-phase7-status-after-7bc.md`
- `docs/plans/baseline.md`
- `docs/ops/database-migrations.md`
- `apps/api/alembic/versions/0002_api_keys_expires_at.py`
- `apps/api/tests/test_phase7e_api_key_expiry.py`
- `apps/web/app/o/[org]/p/[project]/traces/page.tsx`
- `apps/web/app/o/[org]/p/[project]/traces/traces-auto-refresh.tsx`
- `apps/web/tests/security.test.mjs`

`AGENTS.md`, `CLAUDE.md`, and repo-local `MEMORY.md` were not present in this
checkout.

## 1. Objective and Status

7E was split into two deliveries with different risk profiles:

- 7E-backend: `ApiKey.expires_at` lifecycle and auth enforcement.
- 7E-frontend: traces auto-refresh polling UX.

Current status on `main`:

- 7E-backend: implemented/integrated (PR #6, merge `b4ffed2`).
- 7E-frontend: implemented/integrated (PR #7, merge `f44ed19`, commit `1b21b2b`).

This document is no longer a pre-implementation prompt for 7E.

## 2. Historical Split Evidence

### 2.1 Backend split (PR #6)

- Merge: `b4ffed2ded2cd01c78cdbd23ab710ea149aa8f7d`.
- Commit: `2ff9070 feat(evalops): add api key expiration`.
- Migration: `apps/api/alembic/versions/0002_api_keys_expires_at.py`.
- Behavior: generic 401 for expired API key before scope/rate-limit/`last_used_at`.
- Tests: `apps/api/tests/test_phase7e_api_key_expiry.py`.

### 2.2 Frontend split (PR #7)

- Branch: `phase-7e-frontend-polling`.
- Commit: `1b21b2b feat(web): add traces auto refresh`.
- Merge on `main`: `f44ed19 Merge pull request #7 from rouggerxavier/phase-7e-frontend-polling`.
- Main files:
  - `apps/web/app/o/[org]/p/[project]/traces/page.tsx`
  - `apps/web/app/o/[org]/p/[project]/traces/traces-auto-refresh.tsx`
  - `apps/web/tests/security.test.mjs`
- Review record: no P0/P1/P2; `next-env.d.ts` restored and excluded from merge.

## 3. Implemented Contracts (7E)

| Area | Implemented state | Evidence |
|---|---|---|
| API key model/schema | `ApiKey.expires_at` nullable and exposed in list/create shapes. | PR #6 + model/schema/service updates. |
| Auth enforcement | Expired key rejected with generic 401 before scope/rate-limit/`last_used_at`. | `deps.get_project_from_api_key` + phase7E backend test. |
| Migration | `0002_api_keys_expires_at` exists and is reversible. | Alembic revision file in `apps/api/alembic/versions/`. |
| Traces auto-refresh | Client component does bounded polling with `router.refresh()`. | `traces-auto-refresh.tsx`. |
| Server data path preserved | `page.tsx` stays server component with server-side `resolveProject()`/`getTraces()`. | `traces/page.tsx`. |
| Visibility pause | Polling pauses while tab is hidden (`document.hidden` + `visibilitychange`). | `traces-auto-refresh.tsx`. |
| Cursor guard | Auto-refresh disabled on paged cursor views. | `traces/page.tsx` (`Pausado em página paginada`). |
| Manual refresh | Explicit manual refresh action kept. | `Atualizar agora` button. |
| Duplicate client fetch avoidance | No direct `fetch()` introduced in polling component. | Source-level test in `security.test.mjs`. |

## 4. UI/UX Polling Assessment (UI UX Pro Max)

Assessment scope: traces page polling UX only.

Verdict:

- The implementation is appropriate for MVP operations and respects the original guardrails.

Findings:

- High: resolved. Polling is functional (`router.refresh()`), not placeholder behavior.
- High: resolved. Visibility-aware pause reduces hidden-tab load.
- Medium: resolved. Cursor-page guard avoids confusing refresh on paginated state.
- Medium residual risk: polling load still scales by visible open tabs.
- Low residual risk: this remains polling, not realtime/WebSocket.

## 5. Remaining Risks and Follow-up (without reopening 7E)

7E should remain closed unless new defects are found. Residual risks should be
handled as explicit follow-ups:

- Polling load per open visible tab may require interval tuning by telemetry.
- Default interval (`30s`) may need adjustment for specific demos or ops usage.
- If realtime is required later, that is a new scope (SSE/WebSocket), not 7E rework.

## 6. Out of Scope (kept unchanged)

- Redis/distributed rate limit implementation.
- Cleanup jobs for `RevokedToken`/`ExportJob`/export files.
- SDK behavior changes.
- New migrations beyond `0002_api_keys_expires_at`.
- Broad 7B service/router refactor.

## 7. Acceptance Checklist (post-merge view)

- [x] Backend expiry column/migration implemented (`0002_api_keys_expires_at`).
- [x] Backend expiry enforcement implemented with generic 401 behavior.
- [x] Backend phase7E tests exist for expiry behavior.
- [x] Frontend polling implemented with `router.refresh()`.
- [x] Frontend polling has interval lifecycle cleanup.
- [x] Visibility pause implemented (`document.hidden`/`visibilitychange`).
- [x] Manual refresh remains available.
- [x] Cursor-page guard implemented.
- [x] Frontend source-level tests cover polling contracts.
- [x] This documentation round did not run product tests or migrations.

## 8. Decision Log Update

- Decision kept: split backend and frontend deliveries to reduce coupling risk.
- Decision closed: frontend polling is now integrated and should not be reimplemented.
- Next default decision: move to 7F planning (spec-first) for operational readiness.

## 9. Next Recommended Prompt

Use after documental review approval:

```text
Você está no EvalOps em main.

Tarefa: planejar somente 7F (Redis/distributed rate limit + cleanup jobs), sem
implementar código ainda.

Escopo do spec:
- arquitetura de rate limit para multi-worker;
- política de cleanup para RevokedToken/ExportJob e arquivos de export;
- política de falha Redis, idempotência, dry-run, observabilidade e rollback.

Restrições:
- não alterar backend/frontend/SDK/migrations nesta rodada;
- não fazer commit/push;
- preparar material para code review documental.
```
