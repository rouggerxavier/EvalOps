# EvalOps current state audit - 2026-05-19

Scope: documentary audit plus light code audit of the current EvalOps checkout.
No product tests, builds, migrations, Docker, VM commands, staging, commits, or
pushes were run. This document does not change backend, frontend, SDK, schema,
migrations, or deploy state.

## 1. Snapshot

| Item | Result |
|---|---|
| Repo | `/home/rouggerxavier/dev/evalops` |
| Branch | `main` |
| HEAD | `f738c87 docs(evalops): record Oracle VM rollout` |
| Origin sync | `HEAD...origin/main` = `0 0`; local `main` aligned with `origin/main` after `git fetch --prune origin` |
| Initial worktree | clean (`git status --short` empty) |
| Final worktree | docs-only new audit doc |
| Repo-local guidance files | no `AGENTS.md`, `CLAUDE.md`, or `MEMORY.md` in this checkout |
| Framework skills used | `agent-framework-router`, then `project-context-loader` and `diff-reviewer` lens |
| Product commands intentionally skipped | tests, build, migrations, Docker, VM/deploy |

Router result:

- Intent: documentary/current-state audit with light code and commit review.
- Assets selected: `project-context-loader` for repo map, `diff-reviewer` for
  commit/status risk classification.
- UI/UX deep audit was not used; only source-level frontend evidence relevant
  to phase status was inspected.

Observed stack:

- API: FastAPI, SQLAlchemy, Alembic, pytest, SQLite dev/test, Postgres prod path.
- Web: Next.js 15, React, Node test script in `apps/web/tests/security.test.mjs`.
- SDK: Python package under `packages/sdk-python`.
- Ops: `docker-compose.yml`, `docker-compose.prod.yml`, Alembic runbook, Oracle
  VM rollout record, Redis-backed rate-limit ops guide.

## 2. Documentation map

| Document | Category | Status | Current source? | Note |
|---|---|---|---|---|
| `README.md` | MVP / repo entry | needs reconcile | partial | Phase 7 is no longer just "current"; it is closed for this remediation cycle except monitoring/debt. |
| `apps/api/README.md` | MVP / API | useful | partial | Good implementation map; secondary to code and current docs. |
| `apps/web/README.md` | MVP / web | can confuse | no | Still says `EVALOPS_DASHBOARD_BEARER_TOKEN` is required; auth/session flow has evolved. |
| `packages/sdk-python/README.md` | SDK / MVP | current | yes for SDK usage | Includes retry, dead-letter, replay caveats. |
| `docs/README.md` | docs index | useful but stale | partial | Good original index; does not distinguish current status vs historical plans. |
| `docs/00-project-overview.md` | product/MVP | historical useful | no | Product intent, not operational status. |
| `docs/01-product-requirements.md` | product/MVP | historical useful | no | Requirements/backlog; contains future items. |
| `docs/02-user-personas-and-use-cases.md` | product/MVP | historical useful | no | Personas/use cases. |
| `docs/03-mvp-scope.md` | MVP | historical useful | no | Defines original MVP scope; not completion proof. |
| `docs/04-system-architecture.md` | architecture/MVP | historical useful | partial | Architecture target; verify against code before implementation. |
| `docs/05-domain-model.md` | domain/MVP | historical useful | partial | Domain vocabulary; has future retention/event ideas. |
| `docs/06-data-model.md` | data/MVP | historical useful | partial | Conceptual schema; Alembic files are operational schema source. |
| `docs/07-api-spec.md` | API/MVP | historical useful | partial | Contract intent; code/tests are stronger source for exact current behavior. |
| `docs/08-tracing-and-events-spec.md` | phases 1-2 | historical useful | partial | Trace contract intent. |
| `docs/09-evaluation-engine-spec.md` | phases 4-5 | historical useful | partial | Evaluation design; includes future async/schedule ideas. |
| `docs/10-prompt-and-model-versioning.md` | phases 5 | historical useful | partial | Prompt/dataset/experiment domain source. |
| `docs/11-dashboard-and-analytics.md` | frontend/product | historical useful | no | UX target, not source of shipped status. |
| `docs/12-human-feedback-and-datasets.md` | phases 5-6 | historical useful | partial | Feedback/export intent. |
| `docs/13-security-privacy-and-compliance.md` | security/product | historical useful | partial | Good principles; some future/privacy items remain backlog. |
| `docs/14-implementation-roadmap.md` | product roadmap | historical useful | no | Original macro roadmap: Phase 1.1, Phase 2, Phase 3 are post-MVP/product, not remediation Phase 8. |
| `docs/15-testing-strategy.md` | MVP/testing | historical useful | partial | Strategy; current test files/logs are stronger evidence. |
| `docs/16-deployment-and-devops.md` | ops/deploy | historical useful | partial | Original target; current ops sources are `docs/ops/*` and rollout audit. |
| `docs/17-risks-tradeoffs-and-open-questions.md` | product/future | historical useful | no | Backlog/open questions. |
| `docs/18-portfolio-positioning.md` | product/portfolio | historical useful | no | Narrative, not implementation source. |
| `docs/19-execution-plan.md` | MVP plan | historical useful | no | Original execution order. |
| `docs/20-implementation-task-breakdown.md` | MVP plan | historical useful | no | Planning prompts; paths may differ from actual code. |
| `docs/21-mvp-acceptance-checklist.md` | MVP gate | needs reconcile | no | Useful checklist, but unchecked items may not reflect later remediation status. |
| `docs/22-phase-gates-and-validation.md` | MVP gates | historical useful | partial | Gate model; not current status. |
| `docs/23-agent-implementation-prompts.md` | plans/prompts | historical can confuse | no | Prompts are implementation history, not current instructions. |
| `docs/24-codebase-audit.md` | audit | historical can confuse | no | 2026-04-29 snapshot; many repo facts changed. |
| `docs/25-phase7-release-report.md` | audit/release | historical can confuse | no | 2026-04-29 release report predates later Phase 7 remediation. |
| `docs/frontend-audit.md` | audit/frontend | historical useful | no | Frontend snapshot; use only with code verification. |
| `docs/design-refactor-plan.md` | product/frontend future | historical useful | no | Design/product backlog, not completion proof. |
| `docs/audits/evalops-full-codebase-audit.md` | audit | historical useful | no | Critical 2026-05-15 audit; many findings were closed later. Must reconcile before use. |
| `docs/audits/evalops-phase7-status-after-7bc.md` | Phase 7/remediation audit | source current | yes | Current Phase 7 status and accepted 7B debt. |
| `docs/audits/evalops-oracle-vm-rollout-2026-05-19.md` | ops/rollout audit | source current | yes for VM rollout | Records real VM rollout and residual ops risks. |
| `docs/audits/evalops-wsl-performance-diagnostic.md` | audit/perf | historical useful | no | Environment diagnostic only. |
| `docs/ops/database-migrations.md` | ops/deploy | source current | yes | Operational migration source. |
| `docs/ops/rate-limit-and-cleanup.md` | ops/deploy | source current | yes | Operational Redis/cleanup source. |
| `docs/plans/baseline.md` | validation/status ledger | source current with caution | yes, but heavy | Append-style historical ledger; latest sections matter, old sections can confuse. |
| `docs/plans/evalops-remediation-roadmap.md` | remediation roadmap | source current | yes | Current remediation status summary; old body sections remain historical. |
| `docs/plans/evalops-phase7-next-steps.md` | Phase 7 next/current ops | source current | yes | Best current "what next" doc after 7F rollout. |
| `docs/plans/evalops-phase7-execution-plan.md` | Phase 7 historical plan | historical can confuse | no | Already banners itself as historical after 7B/7C. |
| `docs/plans/evalops-phase7d-sdk-dead-letter-spec.md` | Phase 7D spec | historical useful | partial | Spec and decisions; code/SDK README prove implementation. |
| `docs/plans/evalops-phase7e-api-key-expiry-polling-spec.md` | Phase 7E spec | historical useful | partial | Completed spec; use as history plus code evidence. |
| `docs/plans/evalops-phase7f-redis-cleanup-spec.md` | Phase 7F spec | source current-ish | yes for 7F context | Refreshed after 7F-D/rollout; includes historical "before" sections. |
| `docs/plans/evalops-fix-7b-execution-plan.md` | fix plan | historical can confuse | no | Old plan for audit blockers; many items now closed. |
| `docs/decisions/ADR-0001-tech-stack.md` | ADR | source historical decision | partial | Architecture decision record. |
| `docs/decisions/ADR-0002-mvp-scope.md` | ADR | source historical decision | partial | MVP scope decision. |
| `docs/decisions/ADR-0003-evaluation-strategy.md` | ADR | source historical decision | partial | Evaluation strategy decision. |
| `docs/decisions/ADR-0004-tracing-data-model.md` | ADR | source historical decision | partial | Trace model decision. |
| `docs/decisions/ADR-0005-auth-and-api-keys.md` | ADR | source historical decision | partial | Auth/key decision. |
| `docs/examples/*` | examples/fixtures | context fixture | no | Treat as examples only, not rigid contracts. |

## 3. Recommended sources of truth

Current status:

- `docs/audits/evalops-phase7-status-after-7bc.md`
- `docs/plans/evalops-phase7-next-steps.md`
- latest sections of `docs/plans/baseline.md`
- `git log --format='%h %ad %s' --date=short -40`

Operations:

- `docs/ops/database-migrations.md`
- `docs/ops/rate-limit-and-cleanup.md`
- `docs/audits/evalops-oracle-vm-rollout-2026-05-19.md`
- `docker-compose.prod.yml` for production-flavoured compose, noting the VM
  currently uses manual Docker + SQLite.

Remediation roadmap:

- `docs/plans/evalops-remediation-roadmap.md`
- `docs/plans/evalops-phase7-next-steps.md`

Product/future roadmap:

- `docs/14-implementation-roadmap.md`
- `docs/17-risks-tradeoffs-and-open-questions.md`
- product specs `docs/01-*` through `docs/13-*`
- `docs/design-refactor-plan.md`

Do not use without reconciliation:

- `docs/audits/evalops-full-codebase-audit.md`
- `docs/plans/evalops-fix-7b-execution-plan.md`
- `docs/24-codebase-audit.md`
- `docs/25-phase7-release-report.md`
- early sections of `docs/plans/baseline.md`

## 4. Last 40 commits by area

| Commit | Theme | Phase/area | Evidence | Impact |
|---|---|---|---|---|
| `f738c87` | Oracle VM rollout docs | ops / 7F | rollout audit and status docs | Current top-level rollout record. |
| `935c3dc` | Merge PR #11 | 7F-D | merge of cleanup CLI branch | Brings CLI ops maintenance to main. |
| `2980396` | Cleanup CLI | 7F-D | `app.maintenance.cleanup`, CLI tests | Real runnable cleanup surface. |
| `5e785f0` | 7F ops guide | 7F-D docs | `docs/ops/rate-limit-and-cleanup.md` | Operational runbook. |
| `61592ff` / `b3a3242` | Cleanup jobs | 7F-C | cleanup service/tests | Revoked token/export retention hygiene. |
| `ba0978e` / `1af8017` | Redis rate limit | 7F-B | `RedisRateLimiter`, config, tests | Optional shared rate-limit backend. |
| `63da5af` / `abb331b` | Rate limiter abstraction | 7F-A | `RateLimiterBackend`, tests | Preserved facade, enabled Redis follow-up. |
| `f44ed19` / `1b21b2b` | Traces auto refresh | 7E frontend | `TracesAutoRefresh`, web source tests | Bounded polling via `router.refresh()`. |
| `b4ffed2` / `2ff9070` | API key expiry | 7E backend | migration `0002`, deps/tests | Expired keys rejected. |
| `2db73ba` / `4ab910b` | SDK dead-letter replay | 7D | SDK uploader/API/tests/README | Retry/drop + dead-letter/replay implemented. |
| `227de7e`, `0812b76`, `0ab562e` | Phase 7 docs/status | 7A-7D docs | baseline/roadmap/status docs | Reconciled roadmap after smoke/merges. |
| `f13f24c` / `9e9a517` | Structured logging | 7C | `logging_config.py`, `request_id.py`, tests | JSON request logs and request ID. |
| `40cf27a` | SDK reliability | SDK / 7D precursor | uploader/tests | Retry/drop/shutdown reliability base. |
| `8bd3357` | Frontend contracts | UX/export | web pages/API proxy/tests | Export download and planned states. |
| `e7f6101` | Evaluator safety | eval/security | evaluator services/tests | Safer public evaluator output. |
| `ab588aa` | Public error safety | API/web security | safe errors, route updates, tests | Sanitized public errors. |
| `b6c962d` | Deploy migrations/web audit | ops/web | compose, README, web deps | Alembic compose path and Next/PostCSS update. |
| `e159d2d` | Judge budget/cost caps | eval/quota | eval/experiment tests | Closed LLM judge budget bypass. |
| `18e5d02` | Quota transactions | quota/storage | usage service/tests | Hardened quota usage. |
| `7a58739` | Logout revocation | auth/frontend | auth actions/tests | Dashboard logout calls backend revoke. |
| `678a650` | Soft delete consistency | privacy/data | trace/export/eval tests | Closed soft-delete leaks. |
| `f8744ad` | Test DB isolation | testing | `apps/api/tests/conftest.py` | Fixed SQLite lock class. |
| `e2b1f2d` | Full codebase audit | audit | audit doc | Historical blocker snapshot. |
| `618e511` | Service/ownership/Alembic | 7A/7B | Alembic, services, ownership | Partial 7B plus migration base. |
| `1d43541` | Phase 6 quota/eval/storage | phase 6 | tests/models/services | Phase 6 implementation. |

## 5. Phase state

| Phase | Real status | Doc evidence | Code/test evidence | Caveat |
|---|---|---|---|---|
| 1 - P0 security/config | complete with normal residual risk | remediation roadmap + baseline | `test_phase8_p0_security.py`, web security tests, config/body limit code | Not rerun today. |
| 2 - auth hardening/rate limit | complete with ops caveats | remediation roadmap + baseline | `test_phase9_auth_hardening.py`, rate-limit service, logout tests | Proxy/trusted IP remains future hardening. |
| 3 - experiments reais | complete | roadmap/baseline | `experiment_service.py`, `routes_phase5.py`, `test_phase5_prompts_datasets_experiments.py` | CLI/regression polish belongs product roadmap. |
| 4 - audit/privacy/exports | complete with follow-ups | roadmap/baseline | audit service, redaction/export services, `test_phase10_audit_privacy_exports.py` | Broader PII/redaction and audit UI remain future/product hardening. |
| 5 - frontend/backend UX contracts | complete for remediation scope | roadmap/baseline | web actions/pages, `apps/web/tests/security.test.mjs` | Frontend E2E coverage remains thin. |
| 6 - quota/eval/storage | complete with scale caveats | roadmap/baseline | `usage_service.py`, `test_phase12_quota_eval_storage.py` | Real Postgres concurrency/load not tested today. |
| 7A - Alembic/migrations | complete | database migrations doc + baseline | `alembic/versions/0001`, `0002`, compose migrate job | Production legacy stamp path remains operator responsibility. |
| 7B - service extraction/ownership | partial, accepted debt | phase7 status/next steps | `app/ownership.py`, services, remaining wrappers in `routes_phase5.py` | Not a blocker; touch opportunistically with Phase 5 router work. |
| 7C - logging/request_id | complete | phase7 status/next steps | `logging_config.py`, `request_id.py`, `test_phase13_logging_request_id.py` | Runtime smoke only if deploying. |
| 7D - SDK retry/dead-letter/replay | complete | 7D spec + phase7 status | `uploader.py`, `replay_dead_letter`, SDK tests/README | `Retry-After` and jitter are follow-ups, not blockers. |
| 7E backend - key expiry | complete | 7E spec/status | `0002_api_keys_expires_at.py`, `deps._is_expired`, phase7E tests | Future migrations need own smoke. |
| 7E frontend - polling | complete | 7E spec/status | `TracesAutoRefresh`, `router.refresh`, web tests | Polling load tuning is future telemetry-driven work. |
| 7F-A - limiter abstraction | complete | 7F spec/status | `RateLimiterBackend`, `InMemoryRateLimiter`, tests | No Redis in this substep by design. |
| 7F-B - Redis backend | complete | 7F spec/status + ops guide | `RedisRateLimiter`, config envs, fake-Redis tests | Real Redis is deploy/ops responsibility per env. |
| 7F-C - cleanup jobs | complete | 7F spec/status + ops guide | `cleanup_expired_*`, cleanup job tests | Actual scheduling external to app. |
| 7F-D - cleanup CLI/ops | complete | phase7 status + ops guide + VM rollout | CLI flags, JSON output, exit codes, CLI tests | Monitor cron/log after rollout. |
| Oracle VM rollout | applied basic rollout | `evalops-oracle-vm-rollout-2026-05-19.md` | docs record Redis/cleanup/API smoke | No VM command was run in this audit. |

Conclusion: the EvalOps remediation cycle through Phase 7 is closed enough to
call the cycle complete. The one deliberately partial item is 7B, classified
and accepted as non-blocking technical debt.

## 6. Is there a phase after 7?

Remediation roadmap: no Phase 8 was found. The current remediation docs end at
Phase 7 / 7F and then move to operational monitoring, 7B opportunistic cleanup,
and explicit deferred follow-ups.

Product roadmap: yes, there are post-MVP/product tracks, but they are not
"Phase 8" of remediation:

- `docs/14-implementation-roadmap.md`: Phase 1.1 hardening, Phase 2 post-MVP,
  Phase 3 future.
- Product future items include async workers, S3/object storage, webhooks,
  drift alerts, OTLP, Stripe, RBAC/SSO, SDK TypeScript, marketplace, better
  dataset snapshots and richer UX.

What is "done now": MVP/remediation hardening through Phase 7, with 7B as
accepted debt and operations requiring monitoring/backups/formalization if the
VM becomes real production.

What is backlog: product evolution and production-grade hardening, not a hidden
Phase 8 remediation blocker.

## 7. What is still missing

| Item | Type | Severity | Why it matters | Next step |
|---|---|---|---|---|
| 7B `routes_phase5.py` wrappers/router coupling | technical debt | P2 | Remaining architectural cleanup explicitly accepted as partial. | Fix only when touching prompts/datasets/experiments routes for real work. |
| Check first scheduled cleanup log on VM | operations | P2 | Confirms cron actually runs after rollout. | Inspect `/var/log/evalops-cleanup.log` after first scheduled run. |
| VM uses manual Docker + SQLite | operations | P2/P1 if real data | Fine for current rollout record, weak for durable production. | Decide whether to formalize deploy, add SQLite backups, or migrate to Postgres. |
| Old rollback container may remain | operations | P3 | Hygiene after rollout. | Remove only after stable observation. |
| Ubuntu 20.04 EOL/ESM on shared VM | operations/infrastructure | P2 | Host-level maintenance risk outside EvalOps code. | Treat as infra follow-up. |
| Legacy DB stamp path for Alembic `0002` not exercised today | operations | P2 | Existing DBs require correct stamp/upgrade sequencing. | Run in staging/disposable clone before real production DB migration. |
| Frontend E2E coverage is minimal | technical debt | P3 | Web regressions can pass source-contract tests. | Add focused e2e only for high-value flows. |
| `apps/web/README.md` auth env guidance stale | documentation | P2 | Can mislead setup/auth expectations. | Update README to session auth + dev fallback reality. |
| Root `README.md` says Phase 7 current | documentation | P3 | Slightly stale status. | Point to current status doc/index. |
| Historical docs lack banners/index separation | documentation | P2 | Future agents can follow old plans. | Add `docs/STATUS.md` or improve `docs/README.md`, then optional banners. |
| Retry-After/jitter in SDK replay/retry | improvement future | P3 | Better rate-limit politeness at scale. | Product/SDK follow-up only if needed. |
| Trusted proxy/IP rate limiting | improvement future | P2 | Login rate limit accuracy behind proxy. | Address before serious public traffic behind proxies. |
| S3/object storage and formal export retention | improvement future | P2 | Local filesystem exports are limited operationally. | Product/ops roadmap, not Phase 7 blocker. |
| Async worker for eval/export | improvement future | P2 | Needed for throughput/latency beyond MVP sync flows. | Product roadmap Phase 1.1/post-MVP. |
| Stripe/RBAC/SSO/OTLP/webhooks/drift alerts | improvement future | P3 | Product expansion. | Post-MVP roadmap planning. |

No current blocker was found for declaring the remediation/MVP-hardening cycle
closed. For paid traffic or durable production data, the real next blockers are
operational: deploy formalization, backups, host maintenance, and environment
smokes.

## 8. Docs that can confuse future agents

- `docs/audits/evalops-full-codebase-audit.md`: still valuable, but many P0/P1
  blockers were fixed after 2026-05-15.
- `docs/plans/evalops-fix-7b-execution-plan.md`: implementation plan for old
  blockers; not current status.
- Early `docs/plans/baseline.md` sections: append-only snapshots contain old
  "pending" states that later sections close.
- `docs/plans/evalops-phase7-execution-plan.md`: historical plan with banners,
  but still contains old "missing" statements.
- `docs/24-codebase-audit.md` and `docs/25-phase7-release-report.md`: April
  state, before later remediation.
- `apps/web/README.md`: stale authentication guidance.
- `docs/21-mvp-acceptance-checklist.md`: unchecked original acceptance items can
  be mistaken for current blockers.
- `docs/14-implementation-roadmap.md`: product/post-MVP roadmap, not the
  remediation roadmap.

## 9. Documentation organization recommendation

Do not move files now. Moving docs would break many relative links and create
large churn for little immediate value.

Recommended minimal next step:

1. Create `docs/STATUS.md` as the single current source for:
   - current repo status;
   - sources of truth;
   - phase 1-7 status;
   - "no remediation Phase 8";
   - real next fronts.
2. Update `docs/README.md` to split the docs into:
   - current status and ops;
   - product/MVP specs;
   - remediation;
   - audits;
   - historical plans;
   - operations/deploy;
   - future/post-MVP.
3. Add short historical banners only to the highest-risk docs:
   - `docs/audits/evalops-full-codebase-audit.md`
   - `docs/plans/evalops-fix-7b-execution-plan.md`
   - `docs/24-codebase-audit.md`
   - `docs/25-phase7-release-report.md`
   - `docs/plans/evalops-phase7-execution-plan.md` already has a banner; keep it.
4. Only later, if link churn is acceptable, consider folders:

```text
docs/
  status/
  product/
  mvp/
  phases/
  remediation/
  audits/
  ops/
  archive/
```

For now, an index/status document is safer than moving files.

## 10. Files changed by this audit

| File | Type | Why |
|---|---|---|
| `docs/audits/evalops-current-state-audit-2026-05-19.md` | docs-only | Preserve current audit and organization recommendation for future agents. |

No code, frontend, backend, SDK, schema, migrations, deploy files, lockfiles, or
runtime files were edited.

## 11. Validations executed

| Command | Result |
|---|---|
| `git fetch --prune origin` | completed |
| `pwd` | `/home/rouggerxavier/dev/evalops` |
| `git rev-parse --show-toplevel` | `/home/rouggerxavier/dev/evalops` |
| `git branch --show-current` | `main` |
| `git rev-parse --short HEAD` | `f738c87` |
| `git status -sb` | `## main...origin/main` before docs edit |
| `git status --short` | empty before docs edit |
| `git rev-list --left-right --count HEAD...origin/main` | `0 0` |
| `git log --oneline --decorate -40` | inspected |
| `git log --format='%h%x09%ad%x09%s' --date=short -40` | inspected |
| `git log -40 --name-status --format='%h %ad %s' --date=short` | inspected |
| `find docs -type f \| sort` | inspected |
| `find . -maxdepth 3 -type f \( -iname "README.md" -o -iname "*.md" \) \| sort` | inspected |
| phase/status `rg` searches requested in prompt | inspected; noisy storage fixtures ignored conceptually |
| `find apps/api/tests -maxdepth 1 -type f \| sort` | inspected |
| `find apps/web/tests -maxdepth 1 -type f \| sort` | inspected |

Post-edit validation is recorded in the final response for this audit.

## 12. Recommended next step

For this cycle: stop treating Phase 7 as open implementation work. EvalOps is
ready to close the remediation/MVP-hardening cycle.

The next real front depends on intent:

- If the goal is to make future agents safe: create `docs/STATUS.md` and update
  `docs/README.md` with a clear current/historical split.
- If the goal is reliable operation on the Oracle VM: monitor cleanup cron,
  confirm Redis/API health, add SQLite backup or formalize deploy.
- If the goal is product evolution: plan post-MVP work from
  `docs/14-implementation-roadmap.md`, not as "Phase 8 remediation".
- If touching Phase 5 routers anyway: clean 7B wrappers opportunistically.
