# EvalOps Phase 7 status after 7F-A merge

Date: 2026-05-18
Branch inspected: `main`
HEAD inspected: `63da5af`
Original status-pass snapshot: `f13f24c`; previous documentation baseline:
`b4ffed2`.
Scope: documentation reconciliation only. No backend, frontend, SDK, test, infra,
or lockfile changes were made as part of this status pass. No product tests were
run in this documentation pass.

Sources used:

- `git log --oneline --decorate -12` on `main`.
- Current code under `apps/api`, `apps/web`, `packages/sdk-python`, and docs.
- PR #6 merge commit `b4ffed2ded2cd01c78cdbd23ab710ea149aa8f7d`.
- PR #7 merge commit `f44ed19` and implementation commit `1b21b2b`.
- PR #8 merge commit `63da5af` and implementation commit `abb331b`.
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
| 7F-A rate limiter abstraction | done | PR #8 (`63da5af`) with `abb331b`; `RateLimiterBackend`, `RateLimitResult`, `InMemoryRateLimiter`, preserved facade in `rate_limit_service.py`, and `apps/api/tests/test_phase7f_rate_limit_service.py`. | No Redis backend by design; behavior remains in-memory/single-process. | Keep as done; do not redo the abstraction. |
| 7F-B Redis backend | pending | No `redis` dependency/import/config getter; dev compose `REDIS_URL` remains unused by app. | Multi-worker consistency remains open; outage policy still must be decided before coding. | Default next candidate for readiness/multi-worker. |
| 7F-C cleanup jobs | pending | `RevokedToken.expires_at` and `ExportJob.expires_at` exist, but no cleanup service/CLI/job exists. | Cleanup automation remains open; `ExportJob` disposition must be decided before coding. | Implement after 7F-B or when cleanup becomes priority. |
| 7F-D ops docs | pending / follow-up | No final Redis/cleanup ops doc exists for shipped behavior. | Cannot finalize until 7F-B/7F-C behavior exists or is deferred. | Update after 7F-B/7F-C. |

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

1. 7F-B Redis backend, after deciding Redis outage policy.
2. 7F-C cleanup jobs, after deciding expired `ExportJob` disposition.
3. 7F-D final ops docs once Redis/cleanup behavior exists or is formally deferred.
4. 7B opportunistic cleanup when phase 5 routers are touched for real work.

Rationale:

- 7E functional split is complete.
- 7F-A is complete and integrated; it lowered 7F-B risk but did not solve
  multi-worker rate limiting.
- 7F-B is now the main operational readiness gap for multi-worker scenarios.
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
- [x] 7F-A rate limiter abstraction implemented.
- [ ] 7F-B Redis backend implemented or formally deferred with trigger conditions.
- [ ] 7F-C cleanup jobs implemented or formally deferred with trigger conditions.
- [ ] 7F-D final ops docs updated after 7F-B/7F-C.

Verification commands/checks for future implementation PRs:

- Git state: `git status --short` clean before coding.
- 7A (new migrations only): disposable DB `alembic upgrade head`/`current`.
- 7B: `rg -n "_project_or_404" apps/api/app`.
- 7E frontend evidence: `rg -n "TracesAutoRefresh|router.refresh|visibilitychange|document.hidden" apps/web`.
- 7F-B: targeted Redis/fallback/outage rate-limit tests.
- 7F-C: targeted cleanup tests.

---

## 6. Recommended Next Operational Prompt

```text
Prompt for Codex: implementar somente 7F-B Redis backend após decisão explícita
de política de outage Redis.

Recomendação inicial de outage:
- API-key limiter fail-open com warning/log seguro para preservar ingest;
- login limiter fallback in-memory durante outage para manter proteção parcial
  contra brute force.

Objetivo:
- adicionar RedisRateLimiter opcional ao facade já abstraído em 7F-A;
- preservar contrato 429/Retry-After/detail;
- provar limite compartilhado, outage policy e higiene de chaves Redis;
- manter default in-memory sem Redis.

Restrições:
- não implementar cleanup jobs;
- não alterar frontend/SDK/migrations;
- não rodar testes de produto;
- não commitar/push;
- entregar pronto para code review antes de commit.
```
