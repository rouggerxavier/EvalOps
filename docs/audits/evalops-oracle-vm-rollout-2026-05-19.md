# EvalOps Oracle VM rollout - 2026-05-19

Date: 2026-05-19
Scope: operational rollout record for Phase 7F on the shared Oracle VM.
Repo state: `main` / `origin/main` clean at `935c3dc`.

This document records the actual rollout performed on the Oracle VM. It is a
deployment/status record only; it does not document secrets and does not imply a
code, schema, migration, frontend, SDK, or DocOps change.

---

## Executive summary

Phase 7 is complete in code and the basic 7F operational rollout was applied on
the Oracle VM shared with DocOps.

- PR #11 was merged into `main`: `feat(evalops): operationalize cleanup maintenance CLI`.
- The VM repo was updated from the older `139ce3d` state to `origin/main` at
  `935c3dc`.
- EvalOps now runs with a real Redis-backed rate limiter in the VM deployment.
- Cleanup maintenance is available through a tested script and an external cron.
- The current EvalOps VM runtime remains manual Docker with SQLite, not Docker
  Compose and not Postgres.
- DocOps was observed on the same VM and was not changed.
- 7B remains a partial/opportunistic follow-up, not a rollout blocker.

---

## Scope

Included:

- Update the EvalOps repo on the VM to current `origin/main`.
- Add a private Docker network for the EvalOps runtime.
- Add Redis as a Docker container reachable by the API container.
- Recreate the existing manual `evalops-api` container with preserved app env
  plus Redis env.
- Validate Redis rate-limit backend selection and behavior.
- Validate cleanup dry-run/apply with zero scanned rows in the observed rollout.
- Install an external cleanup script and cron entry.

Not included:

- No DocOps service changes.
- No migration from SQLite to Postgres.
- No Docker Compose rollout for EvalOps.
- No secrets documented.
- No cleanup of real rows/files; observed cleanup counts were zero.

---

## Environment

Oracle VM:

- Host label: `docops-server`.
- User used for rollout: `ubuntu`.
- EvalOps repo path: `/home/ubuntu/EvalOps`.
- Final VM repo state: `main...origin/main` clean at `935c3dc`.

DocOps observed on the same VM:

- `docops.service` via systemd.
- `nginx`.
- `docops-postgres` container bound to `127.0.0.1:5433`.
- Existing DocOps backup cron at `0 3 * * *`.

DocOps was not touched during the EvalOps rollout.

---

## Deployment state

Before:

- EvalOps repo on the VM was at older commit `139ce3d`.
- EvalOps API was already deployed as a manual Docker container.
- Docker Compose was not the active EvalOps runtime.

After:

- EvalOps repo is clean on `main` / `origin/main` at `935c3dc`.
- `evalops-api` was recreated manually on Docker network `evalops-runtime`.
- `evalops-redis` runs on the same Docker network.
- `/docs` responds through the host port mapping at `http://127.0.0.1:8001/docs`.

Current EvalOps API container:

- Container: `evalops-api`.
- Image: `python:3.12-slim`.
- Bind mount: `/home/ubuntu/EvalOps/apps/api:/workspace`.
- Port mapping: `8001:8000`.
- Preserved env:
  - `APP_ENV=production`.
  - `DATABASE_URL=sqlite:///./evalops.db`.
  - `JWT_SECRET` preserved, value intentionally not documented.
- Added Redis env:
  - `REDIS_URL=redis://evalops-redis:6379/0`.
  - `EVALOPS_RATE_LIMIT_BACKEND=auto`.
  - `EVALOPS_REDIS_TIMEOUT_MS=200`.

Redis container:

- Container: `evalops-redis`.
- Image: `redis:7-alpine`.
- Network: `evalops-runtime`.
- Host ports: none published; Docker shows Redis only as `6379/tcp`.

Docker Compose was intentionally not used for this rollout. The repository's
current compose file is a dev/local shape and would change the runtime/database
model toward a local compose stack. The old stash conflict around
`docker-compose.yml` was resolved and the stash removed; the current file no
longer exposes Postgres on host port 5432.

---

## Rollout decisions

- Keep the VM runtime as the existing manual Docker deployment for this rollout.
- Preserve the existing SQLite database setting on the VM.
- Use Redis only inside the EvalOps Docker network, with no host port exposure.
- Run cleanup via external cron/script rather than an in-app scheduler.
- Avoid the 03:00 cron slot because DocOps backup already uses it.
- Treat 7B as accepted partial/opportunistic debt, not as a Phase 7F blocker.

---

## Validation evidence

Repository:

- GitHub SSH deploy key was configured for the EvalOps repo.
- VM repo updated to `origin/main` at `935c3dc`.
- Final VM repo state was clean: `main...origin/main`.

Redis:

- `evalops-redis` container started on `evalops-runtime`.
- Redis responded with `PONG`.
- Redis has no published host port.

API and rate limit:

- `evalops-api` was recreated with the preserved app env plus Redis env.
- Backend selection inside `evalops-api` reported `RedisRateLimiter`.
- Rate-limit smoke inside the container:
  - hit 1: `None`.
  - hit 2: `None`.
  - hit 3: `Retry-After` number observed, examples included `25` and `42`.
  - reset path validated.
- API docs endpoint returned `HTTP 200 OK` at `http://127.0.0.1:8001/docs`.

Cleanup CLI:

- Dry-run inside the container returned:
  - `ok: true`
  - `errors: 0`
  - `scanned: 0`
  - `skipped_unsafe: 0`
- Manual apply inside the container returned:
  - `ok: true`
  - `errors: 0`
  - `scanned: 0`
  - `deleted_rows: 0`
  - `deleted_files: 0`

Cleanup script and cron:

- Script path: `/home/ubuntu/run-evalops-cleanup.sh`.
- Script command:

```bash
docker exec -w /workspace evalops-api python -m app.maintenance.cleanup --target all --limit 1000 --apply --json
```

- Script was tested manually and returned `ok: true`.
- Cleanup log path: `/var/log/evalops-cleanup.log`.
- Cron was installed for EvalOps cleanup.
- Operational expected cron state after the rollout adjustment:
  - DocOps backup: `0 3 * * *`.
  - EvalOps cleanup: `15 3 * * *`.

The EvalOps cron was initially placed at 03:00 and then adjusted to 03:15 to
avoid colliding with the existing DocOps backup slot. The final 03:15 state is
recorded here as the expected operational state after that adjustment.

---

## Rollback and observations

- During diagnosis there was an accidental rollback of the `evalops-api`
  container state; the container was recreated again with Redis env and
  revalidated.
- An old rollback container named like `evalops-api-prev-*` may be removed
  after a stable observation period if it still exists.
- Rate-limit rollback remains simple: remove Redis env or set
  `EVALOPS_RATE_LIMIT_BACKEND=memory`, then recreate/restart the API container.
- Cleanup rollback is to remove or disable the external cron/script. If a future
  apply run deletes data that must be restored, use database/filesystem backups.

---

## Residual risks

- The VM runtime is still manual Docker and is not yet formalized as a
  production compose/deploy definition.
- The current VM database is still SQLite.
- `/var/log/evalops-cleanup.log` should be checked after the first scheduled
  cleanup run.
- Ubuntu 20.04 EOL/ESM is an infrastructure risk for the shared VM, outside the
  EvalOps code scope.
- 7B remains partial/opportunistic follow-up debt.

---

## Next operational checks

After the first scheduled run:

```bash
tail -n 100 /var/log/evalops-cleanup.log
```

Confirm runtime containers:

```bash
docker ps --filter name=evalops-api --filter name=evalops-redis
```

Confirm Redis-backed limiter remains active from inside `evalops-api` by
checking the backend reports `RedisRateLimiter`.

Confirm the API docs endpoint still returns `HTTP 200 OK` on
`http://127.0.0.1:8001/docs`.
