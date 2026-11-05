# EvalOps API

FastAPI backend for EvalOps Studio.

## Implemented scope

- Identity and tenancy: users, orgs, projects, memberships
- API keys: create/list/revoke with hashed storage
- Tracing: ingest/list/detail/delete
- Project Quality Gate: persistent configuration, computed pass/review/fail status
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

## Measuring an agent

Rubric evaluators must point to a known path (`trace.output.text`,
`trace.conversation.transcript`, `trace.metadata.*`). An evaluator with nothing to
read, or that fails to run, records an `error`, stays out of the score and leaves
the verdict empty instead of failing the answer. Runs with an error, or partial
runs, can be evaluated again; what they spent stays in the judge budget.

The judge model picks the provider by prefix, with the key in the environment:
`openai/` (`OPENAI_API_KEY`), `openrouter/` (`OPENROUTER_API_KEY`), `gemini/`
(`GEMINI_API_KEY`), `groq/` (`GROQ_API_KEY`). Its cost is an estimate from text
length, and a model outside the price table uses a high fallback price, so set
`cost_cap_usd` in the evaluator config. `repeats` (1 to 5) calls the judge several
times and records the spread in `stddev`. A judge that returns `"flags": ["slug"]`
triggers `critical_flags` with `auto_fail` and `automatic_fail_conditions` on `flag`.

With Redis and the worker running, evaluate many traces and read the results:

```text
POST /v1/projects/{id}/evaluations/batch        {"rubric_id": "...", "batch": "bateria-1"}
GET  /v1/projects/{id}/rubrics/{rubric_id}/report?window=30d&batch=bateria-1
```

Both accept a member's token or `X-EvalOps-Key`. The batch route needs a key
created with the `evaluate` scope, which is never a default; the report needs `read`.

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

- `tests/test_quality_gate.py` (calculation, configuration, ownership, migration rollback)
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
