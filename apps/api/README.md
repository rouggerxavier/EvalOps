# EvalOps API

FastAPI backend for EvalOps Studio.

## Implemented scope

- Identity and tenancy: users, orgs, projects, memberships
- API keys: create/list/revoke with hashed storage
- Tracing: ingest/list/detail/delete
- Analytics overview
- Rubrics and evaluations (sync)
- Prompts, datasets, experiments
- Human feedback and JSONL exports
- Usage counters and mock quotas

## Run locally

```bash
cd apps/api
python -m venv .venv
.venv\Scripts\activate
pip install -c requirements.lock -e .[dev]
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

After changing dependencies, regenerate the versions pinned by `requirements.lock`:

```bash
uv pip compile pyproject.toml --extra dev --universal --python-version 3.12 -o requirements.lock
```

Every organization starts on the `free` plan (1000 traces and 500 evaluations per
month). Operators change one organization's limits with:

```bash
python scripts/set_org_limits.py --org my-org --traces 100000 --evals 20000
```

Health and docs:

- `GET /health/liveness`
- `GET /health/readiness`
- `GET /docs`

## Test

```bash
pytest -q
```

Phase-based suites:

- `tests/test_phase1_identity_access.py`
- `tests/test_phase2_tracing.py`
- `tests/test_phase3_analytics.py`
- `tests/test_phase4_rubrics_eval.py`
- `tests/test_phase5_prompts_datasets_experiments.py`
- `tests/test_phase6_feedback_export_usage.py`
- `tests/test_phase7_e2e_mvp_flow.py`

## Release smoke

```bash
python scripts/smoke_hosted.py --base-url http://localhost:8000
```
