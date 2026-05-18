# EvalOps Phase 7 status after 7E-backend and 7E-frontend merges

Date: 2026-05-18
Branch inspected: `main`
HEAD inspected: `f44ed19`
Original status-pass snapshot: `f13f24c`; previous documentation baseline:
`b4ffed2`.
Scope: documentation reconciliation only. No backend, frontend, SDK, test, infra,
or lockfile changes were made as part of this status pass.

Sources used:

- `git log --oneline --decorate -12` on `main`.
- Current code under `apps/api`, `apps/web`, `packages/sdk-python`, and docs.
- PR #6 merge commit `b4ffed2ded2cd01c78cdbd23ab710ea149aa8f7d`.
- PR #7 merge commit `f44ed19` and implementation commit `1b21b2b`.
- Existing docs:
  `docs/plans/evalops-remediation-roadmap.md`,
  `docs/plans/baseline.md`,
  `docs/plans/evalops-phase7-next-steps.md`,
  `docs/plans/evalops-phase7e-api-key-expiry-polling-spec.md`,
  `docs/ops/database-migrations.md`.

`AGENTS.md`, `CLAUDE.md`, and repo-local `MEMORY.md` were not present in this
checkout.

---

## 1. Current Phase 7 State

| Subphase | Real status | Evidence | Remaining gaps | Next step |
|---|---|---|---|---|
| 7A Alembic / migrations | done | `618e511` + `b6c962d` + documented disposable Postgres smoke for `0001_baseline`; migration `0002` shipped in PR #6. | Production migration execution remains an operator step outside this doc pass. | Keep migration discipline per PR with disposable smoke. |
| 7B service extraction / ownership helper | partial | `618e511` introduced ownership/services and router adoption in `routes.py` + `routes_phase6.py`. | `routes_phase5.py` still has `_project_or_404` wrappers and router/service coupling debt. | Keep opportunistic follow-up while touching phase 5 routers. |
| 7C structured logging / request_id | done | `9e9a517` implemented middleware/context + tests. | No known blocker in current scope. | Do not reimplement without new evidence. |
| 7D SDK retry / dead-letter | done | `40cf27a` + `4ab910b` / PR #5. | No known blocker in current scope. | Do not reimplement without new evidence. |
| 7E-backend `ApiKey.expires_at` | done | PR #6 (`b4ffed2`) + `2ff9070` + migration `0002_api_keys_expires_at` + backend tests. | None in this doc pass beyond normal migration governance. | Keep as done. |
| 7E-frontend traces polling | done | PR #7 merge `f44ed19`; commit `1b21b2b feat(web): add traces auto refresh`; files `traces/page.tsx`, `traces-auto-refresh.tsx`, `apps/web/tests/security.test.mjs`; source evidence for `router.refresh`, `setInterval`, `visibilitychange`, `document.hidden`, manual refresh label, cursor guard. | Residual operational risk: polling load scales per visible tab; interval may need tuning. Not realtime/WebSocket. | Keep implementation; only refine via separate follow-up if needed. |
| 7F Redis rate limit / cleanup jobs | pending / follow-up | Redis exists in compose/env, but rate-limit service remains in-memory and no cleanup job is present for expired `RevokedToken`/`ExportJob`. | Multi-worker consistency and cleanup automation remain open. | Default next candidate: write/review 7F spec, then implement. |

---

## 2. 7E Frontend Completion Evidence

Observed implementation behavior in current `main`:

- `apps/web/app/o/[org]/p/[project]/traces/page.tsx` remains a server component and keeps server-side `resolveProject()` + `getTraces()`.
- `apps/web/app/o/[org]/p/[project]/traces/traces-auto-refresh.tsx` is a client component dedicated to refresh controls and `router.refresh()`.
- Polling loop uses `window.setInterval` with cleanup (`window.clearInterval`).
- Visibility handling uses `document.hidden` and `visibilitychange` listener with removal on unmount.
- Manual refresh remains available (`Atualizar agora`).
- Cursor pagination guard disables auto-refresh when `cursor` is present (`Pausado em página paginada`).
- No duplicate client-side fetch path was introduced in the polling component.

Review evidence (as documented in project context for PR #7):

- `npm run test` passed.
- `npm run build` passed.
- `npx tsc --noEmit` passed.
- Final review approved with no P0/P1/P2 findings.
- Local artifact `apps/web/next-env.d.ts` was restored and did not enter merge.

---

## 3. UI/UX Polling Assessment (UI UX Pro Max)

Scope: traces auto-refresh UX only.

General verdict:

- Fit for MVP operations with explicit control and bounded behavior.

Prioritized findings:

- High: solved. Auto-refresh is real (`router.refresh()`), not placeholder behavior.
- High: solved. Background churn is mitigated by visibility pause.
- Medium: solved. Cursor-page guard avoids confusing automatic refresh on paginated views.
- Medium: open follow-up risk. Polling load is proportional to open visible tabs.
- Low: communication risk. Polling should continue to be described as polling (not realtime/WebSocket).

Recommended follow-up (optional, non-blocking):

- Revisit interval defaults only after production-like telemetry.
- Keep manual refresh and compact status feedback as primary operator affordance.

---

## 4. Updated Next Order

1. 7F Redis/distributed rate limit + cleanup jobs, starting with a spec (no direct implementation first).
2. Release notes/final docs closure for 7E backend+frontend split.
3. 7B opportunistic cleanup when phase 5 routers are touched for real work.

Rationale:

- 7E functional split is complete.
- 7F is now the main operational readiness gap for multi-worker scenarios.
- 7B remains technical debt but is less urgent than 7F for readiness.

---

## 5. Updated Completion Criteria

Blocking for full Phase 7 close:

- [x] 7A migration path validated (including disposable Postgres smoke).
- [ ] 7B follow-up completed or explicitly accepted as debt.
- [x] 7C structured logging/request_id implemented.
- [x] 7D SDK retry/dead-letter/replay implemented.
- [x] 7E-backend `ApiKey.expires_at` implemented.
- [x] 7E-frontend traces polling implemented.
- [ ] 7F Redis/cleanup implemented or formally deferred with trigger conditions.

Verification commands/checks for future implementation PRs:

- Git state: `git status --short` clean before coding.
- 7A (new migrations only): disposable DB `alembic upgrade head`/`current`.
- 7B: `rg -n "_project_or_404" apps/api/app`.
- 7E frontend evidence: `rg -n "TracesAutoRefresh|router.refresh|visibilitychange|document.hidden" apps/web`.
- 7F: targeted rate-limit and cleanup tests.

---

## 6. Recommended Next Operational Prompt

```text
Prompt for Codex: planejar somente 7F (Redis rate limit + cleanup jobs), sem
implementar código nesta rodada.

Objetivo do spec:
- definir arquitetura de rate limit distribuído para multi-worker;
- definir cleanup de RevokedToken/ExportJob expirados e política de arquivos de
  export;
- definir política de falha Redis, idempotência, dry-run, métricas, rollback e
  critérios de aceite.

Restrições:
- não alterar backend/frontend/SDK/migrations;
- não rodar testes de produto;
- não commitar/push;
- entregar pronto para code review documental.
```
