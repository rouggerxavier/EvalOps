# Database migrations (Alembic) — Phase 7A

This document is the operational reference for managing the EvalOps schema
with Alembic. It covers SQLite (dev/test) and PostgreSQL (prod), including
the migration path for databases that pre-date Alembic.

Related code/files:

- `apps/api/alembic.ini`
- `apps/api/alembic/env.py`
- `apps/api/alembic/versions/0001_baseline_schema.py`
- `apps/api/app/main.py` — lifespan picks Alembic vs `create_all`.
- `apps/api/app/db.py` — single `DATABASE_URL` normaliser used by both
  the app and Alembic.

---

## TL;DR

```bash
cd apps/api

# 1. one-time, brand-new DB (SQLite or empty Postgres):
alembic upgrade head

# 2. legacy DB created by the old create_all path
#    (Phase 1-6 schema already present, no alembic_version row yet):
alembic stamp 0001_baseline

# 3. show current revision
alembic current

# 4. roll forward to latest
alembic upgrade head

# 5. roll back one step
alembic downgrade -1
```

The app respects an environment toggle:

| Env var | Default | Effect |
|---|---|---|
| `EVALOPS_USE_ALEMBIC=1` | unset | FastAPI lifespan runs `alembic upgrade head` instead of `Base.metadata.create_all`. Set this in prod. |
| (unset) | — | Lifespan keeps `Base.metadata.create_all` + `ensure_schema_compatibility`. Used by tests and local SQLite dev. |

Both paths read the same database URL: `DATABASE_URL` (preferred) or
`EVALOPS_DB_URL` (alias accepted by Alembic).

---

## Why `create_all` is still around

The pytest suite (and a few dev scripts) wipe the SQLite file between
runs:

```python
@pytest.fixture(autouse=True)
def reset_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
```

That pattern is incompatible with Alembic's `alembic_version` table — the
row would be erased by every `drop_all` and the next test would re-run
all migrations. Phase 7A keeps `create_all` as the default to avoid
churning the entire test suite in a single PR. Phase 7B+ can revisit
fixtures.

`ensure_schema_compatibility()` in `app/db.py` continues to patch the
single legacy case (`users.password_hash`) for old dev DBs.

---

## SQLite workflow (dev/test)

SQLite has limited ALTER TABLE support, so `env.py` enables
`render_as_batch=True`. Any future `op.alter_column` / `drop_column`
is rewritten by Alembic as the copy-and-rename dance.

```bash
cd apps/api

# fresh DB from migrations:
rm -f evalops.db*
alembic upgrade head

# round-trip:
alembic downgrade base && alembic upgrade head

# offline SQL (for review):
alembic upgrade head --sql
```

`apps/api/evalops.db` is the file referenced by the default
`sqlite:///./evalops.db`, normalised to an absolute path inside
`apps/api/` so the location does not depend on the CWD.

---

## PostgreSQL workflow (prod)

```bash
cd apps/api
export DATABASE_URL=postgresql+psycopg://evalops:****@db:5432/evalops
alembic current
alembic upgrade head
```

Driver: `psycopg>=3.2` (sync). `postgresql+asyncpg://` URLs are
silently rewritten to `postgresql+psycopg://` because the project uses
sync SQLAlchemy.

`docker-compose.prod.yml` documents the Postgres URL today; Phase 7A
does **not** change the compose entrypoint. Operators running prod
should add `alembic upgrade head` to the deployment step before
launching `uvicorn` (a follow-up subfase will land this change
together with logging/observability work).

---

## Migrating an existing database

There are three populations to consider:

### A) Brand-new SQLite or empty Postgres

Nothing exists yet. Just run:

```bash
EVALOPS_USE_ALEMBIC=1 DATABASE_URL=<url> alembic upgrade head
```

`0001_baseline_schema.py` creates the full Phase 1-6 schema (every
table, index, unique constraint, FK, and all Phase 2-6 additions:
`audit_logs.organization_id` nullable, `traces.deleted_at`,
`revoked_tokens`, `plans.monthly_span_limit`,
`plans.monthly_token_limit`, `plans.monthly_judge_budget_usd`,
`usage_counters.spans_ingested`, `usage_counters.tokens_ingested`).

### B) Legacy DB built by `create_all` (the production case today)

Tables already exist with the Phase 6 shape (after the manual
`ALTER TABLE`s documented in `app/models.py` and
`docs/plans/baseline.md` were applied). Do **not** run `alembic
upgrade head` — that would attempt to `CREATE TABLE` rows that
already exist. Stamp instead:

```bash
DATABASE_URL=<url> alembic stamp 0001_baseline
```

This writes the `alembic_version` row without touching schema.
Subsequent deploys can then `alembic upgrade head` normally.

Verify before stamping that the running schema matches the baseline:

```bash
DATABASE_URL=<url> python -c "
from sqlalchemy import inspect
from app.db import engine
print(sorted(inspect(engine).get_table_names()))
"
```

Expected set (26 tables):

```
api_keys, audit_logs, dataset_items, datasets, evaluation_runs,
evaluation_scores, evaluators, events, experiment_runs, experiments,
export_jobs, human_feedback, memberships, organizations, plans,
projects, prompt_versions, prompts, revoked_tokens, rubric_versions,
rubrics, spans, subscriptions, traces, usage_counters, users
```

If a Phase 2-6 ALTER was forgotten on the legacy DB (e.g.
`audit_logs.organization_id` still NOT NULL, `traces.deleted_at`
missing), apply it manually first — the relevant SQL is in
`docs/plans/baseline.md` and inline in `app/models.py` — then stamp.

### C) Test/CI

Leave `EVALOPS_USE_ALEMBIC` unset. `create_all` continues to work and
keeps the suite fast.

---

## Authoring new migrations

```bash
cd apps/api

# autogenerate against an up-to-date DB, then audit the diff:
DATABASE_URL=sqlite:///./tmp_review.db alembic upgrade head
alembic revision --autogenerate -m "add api_keys.expires_at"

# the file lands in apps/api/alembic/versions/<hash>_add_api_keys...
# rename it to a stable, ordered name before committing, e.g.
mv alembic/versions/<hash>_add_api_keys_expires_at.py \
   alembic/versions/0002_api_keys_expires_at.py
# and update `revision = "0002_api_keys_expires_at"` + `down_revision = "0001_baseline"`
```

Rules:

- Never edit a migration that has already been merged.
- Every revision must implement `upgrade()` *and* `downgrade()`.
- For SQLite-safe column changes, wrap edits in
  `with op.batch_alter_table(...) as batch_op:` — `env.py` already
  passes `render_as_batch=True`, so this is the only pattern that
  works on SQLite.
- Numeric IDs (`0002`, `0003`, …) keep filenames sortable; the
  revision string itself can be anything unique.

---

## Validation

What was actually validated in Phase 7A:

| Target | Result |
|---|---|
| `alembic upgrade head` on empty SQLite | ✅ creates 26 tables identical to `create_all` (table names + columns + indexes diff = empty). |
| `alembic downgrade base` round-trip on SQLite | ✅ drops every table; only `alembic_version` remains. |
| `alembic upgrade head` on Postgres | ⏳ **pending** — local Docker not available in this session; smoke needs to be run as part of the prod deploy gate. |
| Test regression (`test_health`, `test_auth_flow`, `test_phase8`, `test_phase12`) with default `create_all` path | see `docs/plans/baseline.md` Phase 7A section. |

---

## Rollback

To unwind Phase 7A:

1. Set `EVALOPS_USE_ALEMBIC=0` (or unset). Lifespan reverts to
   `create_all`.
2. Optional: `DELETE FROM alembic_version` to wipe bookkeeping.

The baseline migration is non-destructive (it only `CREATE TABLE`s),
so no data is lost by toggling the flag off. Future revisions that
mutate columns must include working `downgrade()` paths.
