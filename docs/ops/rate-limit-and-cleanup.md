# Rate limit and cleanup operations — Phase 7F

Date: 2026-05-19
Scope: 7F-D operational documentation and CLI contract for behavior shipped in
7F-B and 7F-C.

This document explains how to operate:

- the optional Redis-backed rate limiter from 7F-B;
- the expired `RevokedToken` / `ExportJob` cleanup CLI from 7F-C.

It does not add schema changes, migrations, frontend behavior, SDK behavior,
or an in-app scheduler.

Real Oracle VM rollout evidence is recorded in
`docs/audits/evalops-oracle-vm-rollout-2026-05-19.md`.

---

## 1. Shipped behavior

### 7F-B rate limiter

Implementation:

- `apps/api/app/domain/services/rate_limit_service.py`
- `apps/api/app/config.py`
- `apps/api/tests/test_phase7f_redis_rate_limit.py`

Runtime selection:

| Env | Default | Meaning |
|---|---|---|
| `EVALOPS_RATE_LIMIT_BACKEND` | `auto` | `memory`, `redis`, or `auto`. |
| `REDIS_URL` | unset | Redis DSN used when backend resolves to Redis. |
| `EVALOPS_REDIS_TIMEOUT_MS` | `200` | Redis connect/op timeout in milliseconds. |

Modes:

- `memory`: always use in-process buckets.
- `redis`: use Redis when `REDIS_URL` is set; fall back to memory with a warning
  if the URL is missing or client initialization fails.
- `auto`: use Redis only when `REDIS_URL` is set; otherwise use memory.

Outage policy:

- API-key limiter: fail-open if the active backend raises. Auth, key expiry and
  scopes still run before the limiter; rate limiting is abuse mitigation.
- Login limiter: fall back to a local in-memory limiter if Redis is unavailable.
  This preserves partial brute-force protection per process.

Redis keys:

- API keys are keyed by `ApiKey.id`, not the raw API key.
- Login buckets use `sha256(email|ip)`, not raw email.
- Fixed-window keys self-expire; no cleanup job is needed for rate-limit keys.

### 7F-C cleanup core and 7F-D CLI

Implementation:

- `apps/api/app/maintenance/cleanup.py`
- `apps/api/tests/test_phase7f_cleanup_jobs.py`
- `apps/api/tests/test_phase7f_cleanup_cli.py`

Default behavior:

- `python -m app.maintenance.cleanup` is dry-run.
- `python -m app.maintenance.cleanup --apply` is required to mutate rows/files.
- `--target all` runs both cleanup targets (default).
- `--target revoked-tokens` runs only expired `RevokedToken` cleanup.
- `--target exports` runs only expired `ExportJob` cleanup.
- `--limit N` bounds the rows scanned per selected target in one invocation.
- `--json` emits one stable JSON object for scheduler/log parsing.
- Human-readable output is a stable summary with counts.
- Exit code `0` means the invocation completed with no cleanup errors.
- A non-zero exit code means an invalid invocation or real cleanup failure.
- No scheduler is started by the API process.
- `ExportJob.file_path` is not trusted for deletion; cleanup reconstructs
  `exports_dir() / f"{job.id}.jsonl"`.
- Symlink/traversal/escape attempts are skipped and the row is preserved.
- Missing export files are idempotent: the row can still be removed.
- `audit_logs` are not touched.

---

## 2. Local validation

From `apps/api`:

```bash
.venv/bin/python -m pytest tests/test_phase7f_redis_rate_limit.py -q --tb=short -p no:warnings
.venv/bin/python -m pytest tests/test_phase7f_cleanup_jobs.py -q --tb=short -p no:warnings
.venv/bin/python -m pytest tests/test_phase7f_cleanup_cli.py -q --tb=short -p no:warnings
```

Cleanup dry-run:

```bash
cd apps/api
.venv/bin/python -m app.maintenance.cleanup
```

Cleanup dry-run for one target with JSON output:

```bash
cd apps/api
.venv/bin/python -m app.maintenance.cleanup --target exports --limit 500 --json
```

Cleanup apply:

```bash
cd apps/api
.venv/bin/python -m app.maintenance.cleanup --apply
```

Run apply only after reviewing the dry-run output for the target environment.

---

## 3. Redis deployment

Single-worker deployments can leave Redis unset and keep the default memory
backend.

Use Redis when the API runs with multiple workers or multiple replicas and the
rate-limit buckets must be shared.

Example production env:

```bash
EVALOPS_RATE_LIMIT_BACKEND=redis
REDIS_URL=redis://redis:6379/0
EVALOPS_REDIS_TIMEOUT_MS=200
```

The current `docker-compose.prod.yml` does not provision a Redis service. Add
one only in the deployment change that actually needs shared rate-limit
buckets, and validate it in that environment.

Basic Redis smoke, when a Redis endpoint is available:

```bash
redis-cli -u "$REDIS_URL" ping
```

Expected result:

```text
PONG
```

---

## 4. Cleanup scheduling

The recommended scheduling model is external cron/platform scheduler. Do not
add an infinite in-app scheduler to FastAPI.

The cleanup command must run with the same environment as the API, especially:

- `DATABASE_URL`
- `EVALOPS_EXPORTS_DIR`
- Python package dependencies installed

### Cron example

Run daily at 03:15:

```cron
15 3 * * * cd /srv/evalops/apps/api && /srv/evalops/apps/api/.venv/bin/python -m app.maintenance.cleanup --apply --json >> /var/log/evalops-cleanup.log 2>&1
```

### Docker Compose one-shot example

If using the production-flavoured compose and the API image context is already
installed the same way as the app service:

```bash
docker compose -f docker-compose.prod.yml run --rm api \
  sh -c "pip install --no-cache-dir -e '.' && python -m app.maintenance.cleanup --json"
```

After reviewing dry-run:

```bash
docker compose -f docker-compose.prod.yml run --rm api \
  sh -c "pip install --no-cache-dir -e '.' && python -m app.maintenance.cleanup --apply --json"
```

For a real deploy, prefer a dedicated scheduled job using the same image/env as
the API rather than a long-running API background task.

### Oracle VM rollout applied

The 2026-05-19 Oracle VM rollout used the existing manual Docker deployment,
not Docker Compose. The active EvalOps API container is `evalops-api`, based on
`python:3.12-slim`, with `/home/ubuntu/EvalOps/apps/api` mounted at
`/workspace` and host port `8001` mapped to container port `8000`.

Redis runs as `evalops-redis` on Docker network `evalops-runtime` with image
`redis:7-alpine`. It has no host port published; the API reaches it through
`REDIS_URL=redis://evalops-redis:6379/0` and
`EVALOPS_RATE_LIMIT_BACKEND=auto`.

Cleanup runs through `/home/ubuntu/run-evalops-cleanup.sh`, which executes:

```bash
docker exec -w /workspace evalops-api python -m app.maintenance.cleanup --target all --limit 1000 --apply --json
```

The expected operational cron split after the rollout adjustment is:

```cron
0 3 * * *  # DocOps backup
15 3 * * * # EvalOps cleanup
```

DocOps runs on the same VM and must not be touched by EvalOps maintenance. Keep
the EvalOps cleanup at 03:15 unless the DocOps backup window changes.

---

## 5. First-run checklist

1. Confirm the target database:

```bash
echo "$DATABASE_URL"
```

2. Confirm the export directory:

```bash
echo "$EVALOPS_EXPORTS_DIR"
```

3. Run dry-run:

```bash
python -m app.maintenance.cleanup --target all --json
```

4. Review counts:

- `deleted_rows`
- `deleted_files`
- `missing_files`
- `skipped_unsafe`
- `errors`
- `unsafe_ids`

5. Investigate non-zero `skipped_unsafe` or `errors` before `--apply`.

6. Run apply:

```bash
python -m app.maintenance.cleanup --apply --target all --json
```

7. Record the output in the deployment log.

---

## 6. Rollback

Rate limiter:

- Set `EVALOPS_RATE_LIMIT_BACKEND=memory`, or unset `REDIS_URL` in `auto` mode.
- Restart API workers.
- This reverts to in-process buckets; multi-worker deployments lose shared
  counters but auth still works.

Cleanup:

- Disable the external scheduler.
- Do not run `--apply`.
- If a cleanup run has already hard-deleted expired rows/files, restore from
  database/filesystem backups if the data is still required. The application
  does not keep a cleanup marker table.

---

## 7. Residual risks

- Redis is optional in code, but production still needs explicit Redis
  provisioning when shared rate-limit buckets are required.
- Redis fixed-window limiting can allow boundary bursts compared with a strict
  sliding window.
- Cleanup hard-deletes expired `RevokedToken` and expired safe `ExportJob` rows.
  Audit logs are preserved, but the row itself is not retained.
- External scheduler installation is environment-specific and is not validated
  by this repository alone.
- Cleanup `--apply` should not be run before reviewing dry-run output in the
  target environment.
