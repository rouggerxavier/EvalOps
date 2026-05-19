# EvalOps Phase 7 status after 7F-D ops maintenance

Date: 2026-05-19
Branch inspected: `phase-7f-d-ops-maintenance`
Base HEAD inspected: `5e785f0`
Post-rollout update: `main` / `origin/main` reached `935c3dc` after PR #11 and
the basic Oracle VM rollout. See
`docs/audits/evalops-oracle-vm-rollout-2026-05-19.md`.
Original status-pass snapshot: `f13f24c`; previous documentation baseline:
`b4ffed2`.
Scope: status reconciliation after PR #9, PR #10, 7F-D ops docs, and 7F-D
cleanup CLI operationalization. No frontend, SDK, schema, migration, infra, or
lockfile changes were made.

Sources used:

- `git log --oneline --decorate -12` on `main`.
- Current code under `apps/api`, `apps/web`, `packages/sdk-python`, and docs.
- Current 7F-D CLI changes in `apps/api/app/maintenance/cleanup.py` and
  `apps/api/tests/test_phase7f_cleanup_cli.py`.
- PR #6 merge commit `b4ffed2ded2cd01c78cdbd23ab710ea149aa8f7d`.
- PR #7 merge commit `f44ed19` and implementation commit `1b21b2b`.
- PR #8 merge commit `63da5af` and implementation commit `abb331b`.
- PR #9 merge commit `ba0978e` and implementation commit `1af8017`.
- PR #10 merge commit `61592ff` and implementation commit `b3a3242`.
- Existing docs:
  `docs/plans/evalops-remediation-roadmap.md`,
  `docs/plans/baseline.md`,
  `docs/plans/evalops-phase7-next-steps.md`,
  `docs/plans/evalops-phase7e-api-key-expiry-polling-spec.md`,
  `docs/plans/evalops-phase7f-redis-cleanup-spec.md`,
  `docs/ops/rate-limit-and-cleanup.md`,
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
| 7F-A rate limiter abstraction | done | PR #8 (`63da5af`) with `abb331b`; `RateLimiterBackend`, `RateLimitResult`, `InMemoryRateLimiter`, preserved facade in `rate_limit_service.py`, and `apps/api/tests/test_phase7f_rate_limit_service.py`. | No remaining 7F-A blocker. | Keep as done; do not redo the abstraction. |
| 7F-B Redis backend | done | PR #9 (`ba0978e`) with `1af8017`; optional `RedisRateLimiter`, `redis_url()`, `rate_limit_backend()`, `redis_timeout_ms()`, `redis>=5,<6`, and `apps/api/tests/test_phase7f_redis_rate_limit.py`. | Production Redis provisioning is an operator/deploy step; code defaults to memory when Redis is absent. | Configure Redis only for environments that need multi-worker shared buckets. |
| 7F-C cleanup jobs | done | PR #10 (`61592ff`) with `b3a3242`; cleanup services, dry-run default, safe export-file unlink, and `apps/api/tests/test_phase7f_cleanup_jobs.py`. | Actual cleanup execution is manual or external scheduler; no in-app scheduler was added. | Keep core cleanup behavior; do not add an in-app scheduler. |
| 7F-D ops maintenance | implemented | `app.maintenance.cleanup` now has stable target selection, limit, JSON output, human summary, exit codes, and `apps/api/tests/test_phase7f_cleanup_cli.py`. | Docs still do not provision Redis, deploy cron, or run production cleanup. | Use during operator/deploy rollout. |

Post-rollout status on 2026-05-19:

- 7F-B, 7F-C, and 7F-D are complete in code/docs scope.
- Oracle VM was validated on `main` / `origin/main` at `935c3dc`.
- Real Redis is active as `evalops-redis` on the EvalOps Docker network with no
  host port published.
- `evalops-api` reported `RedisRateLimiter`.
- Cleanup dry-run/apply returned `ok: true` with zero scanned rows in the
  observed rollout.
- Cleanup script and external cron are installed; expected EvalOps schedule is
  03:15 to avoid the existing DocOps backup at 03:00.
- DocOps was preserved and not modified.
- EvalOps VM runtime remains manual Docker with SQLite, not Docker Compose and
  not Postgres.
- 7B remains partial/opportunistic follow-up debt, accepted as non-blocking for
  Phase 7F rollout.

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

1. Operational monitoring after the Oracle VM rollout: cleanup log, container
   health, and active `RedisRateLimiter` backend.
2. Optional deploy formalization only if operations need to move away from the
   current manual Docker VM runtime.
3. 7B opportunistic cleanup when phase 5 routers are touched for real work.

Rationale:

- 7E functional split is complete.
- 7F-A, 7F-B, and 7F-C are complete in code scope.
- 7F-D is implemented as an operational CLI contract, and the basic Oracle VM
  rollout is applied and validated.
- 7B remains technical debt, but it is separate from the 7F operational tail.

---

## 5. Updated Completion Criteria

Blocking for full Phase 7 close:

- [x] 7A migration path validated (including disposable Postgres smoke).
- [x] 7B follow-up remains partial and is explicitly accepted as opportunistic debt.
- [x] 7C structured logging/request_id implemented.
- [x] 7D SDK retry/dead-letter/replay implemented.
- [x] 7E-backend `ApiKey.expires_at` implemented.
- [x] 7E-frontend traces polling implemented.
- [x] 7F-A rate limiter abstraction implemented.
- [x] 7F-B Redis backend implemented.
- [x] 7F-C cleanup jobs implemented.
- [x] 7F-D cleanup CLI operationalization implemented, documented, and basically rolled out on the Oracle VM.

Verification commands/checks for future implementation PRs:

- Git state: `git status --short` clean before coding.
- 7A (new migrations only): disposable DB `alembic upgrade head`/`current`.
- 7B: `rg -n "_project_or_404" apps/api/app`.
- 7E frontend evidence: `rg -n "TracesAutoRefresh|router.refresh|visibilitychange|document.hidden" apps/web`.
- 7F-B: `cd apps/api && .venv/bin/python -m pytest tests/test_phase7f_redis_rate_limit.py -q --tb=short -p no:warnings`.
- 7F-C: `cd apps/api && .venv/bin/python -m pytest tests/test_phase7f_cleanup_jobs.py -q --tb=short -p no:warnings`.
- 7F-D: `cd apps/api && .venv/bin/python -m pytest tests/test_phase7f_cleanup_cli.py -q --tb=short -p no:warnings`.

---

## 6. Recommended Next Operational Prompt

```text
Prompt para operação/deploy: validar 7F em ambiente alvo sem mudar produto.

Objetivo:
- configurar REDIS_URL e EVALOPS_RATE_LIMIT_BACKEND somente no ambiente que
  precisa de buckets compartilhados entre workers;
- rodar cleanup em dry-run com `python -m app.maintenance.cleanup --json`;
- instalar cron/plataforma externa para chamar `python -m app.maintenance.cleanup --apply --json`;
- registrar logs/resultado da primeira execução.

Restrições:
- não criar scheduler dentro do app;
- não alterar schema/migrations;
- não executar cleanup `--apply` antes de revisar o dry-run no ambiente alvo.
```
