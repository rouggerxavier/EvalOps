from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import User
from app.security import create_access_token

client = TestClient(app)


def _auth_header(user_id: str, email: str, name: str) -> dict[str, str]:
    token = create_access_token(sub=user_id, email=email, name=name)
    return {"Authorization": f"Bearer {token}"}


def _bootstrap() -> tuple[dict[str, str], str, str]:
    with SessionLocal() as db:
        db.add(User(id="usr_1", email="u1@example.com", name="User One"))
        db.commit()
    headers = _auth_header("usr_1", "u1@example.com", "User One")
    org = client.post("/v1/organizations", headers=headers, json={"name": "Acme", "slug": "acme"}).json()
    project = client.post(
        "/v1/projects",
        headers=headers,
        json={"organization_id": org["id"], "name": "DocOps", "slug": "docops"},
    ).json()
    return headers, org["id"], project["id"]


def _create_api_key(headers: dict[str, str], project_id: str) -> str:
    return client.post(
        f"/v1/projects/{project_id}/api-keys",
        headers=headers,
        json={"name": "ingest", "environment": "prod", "scopes": ["ingest", "read"]},
    ).json()["key"]


def _ingest_trace(api_key: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "traces": [
            {
                "client_trace_id": "ct_phase5",
                "name": "docops.summarize",
                "service": "docops-agent",
                "environment": "prod",
                "started_at": now.isoformat(),
                "ended_at": (now + timedelta(milliseconds=1200)).isoformat(),
                "status": "ok",
                "tags": {"feature": "summarization"},
                "metadata": {"trace_type": "agent_response"},
                "spans": [
                    {
                        "client_span_id": "cs_root",
                        "type": "llm_call",
                        "name": "openai.chat.completions",
                        "started_at": (now + timedelta(milliseconds=50)).isoformat(),
                        "ended_at": (now + timedelta(milliseconds=1100)).isoformat(),
                        "status": "ok",
                        "provider": "openai",
                        "model": "gpt-4o-mini",
                        "tokens_in": 200,
                        "tokens_out": 100,
                        "messages_in": [{"role": "user", "content": "Summarize this policy"}],
                        "messages_out": [{"role": "assistant", "content": "Summary"}],
                    }
                ],
            }
        ]
    }
    resp = client.post("/v1/traces", headers={"X-EvalOps-Key": api_key}, json=payload)
    assert resp.status_code == 202
    return resp.json()["results"][0]["trace_id"]


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_prompt_versioning_is_immutable() -> None:
    headers, _, project_id = _bootstrap()
    created = client.post(
        f"/v1/projects/{project_id}/prompts",
        headers=headers,
        json={
            "slug": "support-answer-system",
            "description": "Support prompt",
            "template": "You are helpful. User: {{ user_message }}",
            "variables": {"user_message": {"type": "string", "required": True}},
            "metadata": {"model_default": "openai/gpt-4o-mini"},
            "changelog": "Initial",
        },
    )
    assert created.status_code == 201
    prompt_id = created.json()["prompt"]["id"]
    assert created.json()["version"]["version"] == 1

    v2 = client.post(
        f"/v1/prompts/{prompt_id}/versions",
        headers=headers,
        json={
            "template": "You are very helpful. User: {{ user_message }}",
            "variables": {"user_message": {"type": "string", "required": True}},
            "metadata": {"model_default": "openai/gpt-4.1"},
            "changelog": "Refined wording",
        },
    )
    assert v2.status_code == 201
    assert v2.json()["prompt_version"] == 2

    versions = client.get(f"/v1/prompts/{prompt_id}/versions", headers=headers)
    assert versions.status_code == 200
    data = versions.json()["data"]
    assert len(data) == 2
    assert data[0]["version"] == 1
    assert data[1]["version"] == 2
    assert data[0]["template"] == "You are helpful. User: {{ user_message }}"
    assert data[1]["template"] == "You are very helpful. User: {{ user_message }}"


def test_dataset_item_create_and_list() -> None:
    headers, _, project_id = _bootstrap()
    dataset = client.post(
        f"/v1/projects/{project_id}/datasets",
        headers=headers,
        json={"slug": "golden-support", "description": "Golden set", "source": "manual"},
    )
    assert dataset.status_code == 201
    dataset_id = dataset.json()["id"]

    add_items = client.post(
        f"/v1/datasets/{dataset_id}/items",
        headers=headers,
        json={
            "items": [
                {
                    "input": {"messages": [{"role": "user", "content": "Oi"}]},
                    "expected_output": {"assistant_message": "Ola!"},
                    "metadata": {"source": "manual"},
                },
                {
                    "input": {"messages": [{"role": "user", "content": "Preciso de ajuda"}]},
                    "expected_output": {"assistant_message": "Claro, como posso ajudar?"},
                    "metadata": {"source": "manual"},
                },
            ]
        },
    )
    assert add_items.status_code == 201
    assert add_items.json()["created"] == 2

    listed = client.get(f"/v1/datasets/{dataset_id}/items", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()["data"]) == 2


def test_experiment_with_two_variants_runs_and_returns_summary() -> None:
    headers, _, project_id = _bootstrap()
    api_key = _create_api_key(headers, project_id)
    _ingest_trace(api_key)

    rubric_yaml = """
slug: support-quality
name: Support Quality
description: Minimal rubric
threshold: 0.5
aggregate: weighted_mean
evaluators:
  - id: length_check
    type: length_bounds
    weight: 1.0
    config:
      target: trace.output.assistant_message
      unit: chars
      min: 5
      max: 500
"""
    rubric = client.post(
        f"/v1/projects/{project_id}/rubrics",
        headers=headers,
        json={"yaml_source": rubric_yaml},
    )
    assert rubric.status_code == 201
    rubric_id = rubric.json()["rubric"]["id"]

    dataset = client.post(
        f"/v1/projects/{project_id}/datasets",
        headers=headers,
        json={"slug": "trace-replay", "description": "Replay traces", "source": "traces"},
    )
    assert dataset.status_code == 201
    dataset_id = dataset.json()["id"]

    built = client.post(
        f"/v1/datasets/{dataset_id}/build-from-traces",
        headers=headers,
        json={"environment": "prod", "limit": 10},
    )
    assert built.status_code == 202
    assert built.json()["created"] >= 1

    experiment = client.post(
        f"/v1/projects/{project_id}/experiments",
        headers=headers,
        json={
            "name": "model-comparison",
            "dataset_id": dataset_id,
            "rubric_id": rubric_id,
            "variants": [
                {"name": "control", "model": "openai/gpt-4o-mini", "params": {"temperature": 0.2}},
                {"name": "candidate", "model": "openai/gpt-4.1", "params": {"temperature": 0.2}},
            ],
            "baseline_variant": "control",
            "pass_criteria": {"min_pass_rate": 0.5, "no_regression_vs": "control"},
        },
    )
    assert experiment.status_code == 201
    experiment_id = experiment.json()["id"]

    run = client.post(f"/v1/experiments/{experiment_id}/run", headers=headers, json={"triggered_by": "api"})
    assert run.status_code == 202
    run_id = run.json()["run_id"]
    assert run.json()["status"] in ["completed", "error"]

    detail = client.get(f"/v1/experiments/{experiment_id}/runs/{run_id}", headers=headers)
    assert detail.status_code == 200
    run_data = detail.json()["run"]
    assert "by_variant" in run_data
    assert "control" in run_data["by_variant"]
    assert "candidate" in run_data["by_variant"]
    assert "comparisons" in run_data
    assert "criteria_failures" in run_data


def _seed_prompt_version(headers: dict[str, str], project_id: str, slug: str, template: str) -> None:
    resp = client.post(
        f"/v1/projects/{project_id}/prompts",
        headers=headers,
        json={
            "slug": slug,
            "description": slug,
            "template": template,
            "variables": {"user_message": {"type": "string", "required": True}},
            "metadata": {},
            "changelog": "v1",
        },
    )
    assert resp.status_code == 201


def _keyword_rubric_yaml() -> str:
    return """
slug: kw-presence
name: Keyword Presence
description: Pass when 'hello' appears in assistant output
threshold: 0.5
aggregate: weighted_mean
evaluators:
  - id: kw_hello
    type: keyword_presence
    weight: 1.0
    config:
      target: trace.output.assistant_message
      keywords: ["hello"]
      require: any
"""


def _bootstrap_experiment_pieces(
    headers: dict[str, str], project_id: str
) -> tuple[str, str]:
    api_key = _create_api_key(headers, project_id)
    _ingest_trace(api_key)
    rubric = client.post(
        f"/v1/projects/{project_id}/rubrics",
        headers=headers,
        json={"yaml_source": _keyword_rubric_yaml()},
    )
    assert rubric.status_code == 201
    rubric_id = rubric.json()["rubric"]["id"]

    dataset = client.post(
        f"/v1/projects/{project_id}/datasets",
        headers=headers,
        json={"slug": "ds-exp", "description": "exp set", "source": "traces"},
    )
    assert dataset.status_code == 201
    dataset_id = dataset.json()["id"]

    built = client.post(
        f"/v1/datasets/{dataset_id}/build-from-traces",
        headers=headers,
        json={"environment": "prod", "limit": 10},
    )
    assert built.status_code == 202
    return rubric_id, dataset_id


def test_distinct_variants_produce_distinct_results() -> None:
    headers, _, project_id = _bootstrap()
    rubric_id, dataset_id = _bootstrap_experiment_pieces(headers, project_id)

    _seed_prompt_version(headers, project_id, "with-hello", "hello {{ user_message }}")
    _seed_prompt_version(headers, project_id, "without-hello", "bye {{ user_message }}")

    experiment = client.post(
        f"/v1/projects/{project_id}/experiments",
        headers=headers,
        json={
            "name": "prompt-divergence",
            "dataset_id": dataset_id,
            "rubric_id": rubric_id,
            "variants": [
                {"name": "control", "prompt_version_ref": "with-hello@1"},
                {"name": "candidate", "prompt_version_ref": "without-hello@1"},
            ],
            "baseline_variant": "control",
        },
    )
    assert experiment.status_code == 201
    experiment_id = experiment.json()["id"]

    run = client.post(
        f"/v1/experiments/{experiment_id}/run",
        headers=headers,
        json={"triggered_by": "api"},
    )
    assert run.status_code == 202
    run_id = run.json()["run_id"]

    detail = client.get(
        f"/v1/experiments/{experiment_id}/runs/{run_id}", headers=headers
    )
    assert detail.status_code == 200
    run_data = detail.json()["run"]
    assert run_data["status"] == "completed"
    by_variant = run_data["by_variant"]
    assert by_variant["control"]["pass_rate"] == 1.0
    assert by_variant["candidate"]["pass_rate"] == 0.0
    comparisons = run_data["comparisons"]
    delta = comparisons["candidate_vs_control"]["delta_pass_rate"]
    assert delta != 0
    assert delta == -1.0


def test_identical_variants_produce_identical_results() -> None:
    headers, _, project_id = _bootstrap()
    rubric_id, dataset_id = _bootstrap_experiment_pieces(headers, project_id)

    _seed_prompt_version(headers, project_id, "twin", "hello {{ user_message }}")

    experiment = client.post(
        f"/v1/projects/{project_id}/experiments",
        headers=headers,
        json={
            "name": "twin-variants",
            "dataset_id": dataset_id,
            "rubric_id": rubric_id,
            "variants": [
                {
                    "name": "alpha",
                    "prompt_version_ref": "twin@1",
                    "model": "openai/gpt-4o-mini",
                    "params": {"temperature": 0.2},
                },
                {
                    "name": "beta",
                    "prompt_version_ref": "twin@1",
                    "model": "openai/gpt-4o-mini",
                    "params": {"temperature": 0.2},
                },
            ],
            "baseline_variant": "alpha",
        },
    )
    assert experiment.status_code == 201
    experiment_id = experiment.json()["id"]

    run = client.post(
        f"/v1/experiments/{experiment_id}/run",
        headers=headers,
        json={"triggered_by": "api"},
    )
    assert run.status_code == 202
    run_id = run.json()["run_id"]

    detail = client.get(
        f"/v1/experiments/{experiment_id}/runs/{run_id}", headers=headers
    )
    assert detail.status_code == 200
    run_data = detail.json()["run"]
    assert run_data["status"] == "completed"
    by_variant = run_data["by_variant"]
    assert by_variant["alpha"]["pass_rate"] == by_variant["beta"]["pass_rate"]
    assert by_variant["alpha"]["avg_score"] == by_variant["beta"]["avg_score"]
    assert run_data["comparisons"]["beta_vs_alpha"]["delta_pass_rate"] == 0


def test_invalid_baseline_variant_returns_422() -> None:
    headers, _, project_id = _bootstrap()
    rubric_id, dataset_id = _bootstrap_experiment_pieces(headers, project_id)

    resp = client.post(
        f"/v1/projects/{project_id}/experiments",
        headers=headers,
        json={
            "name": "bad-baseline",
            "dataset_id": dataset_id,
            "rubric_id": rubric_id,
            "variants": [
                {"name": "control", "model": "x"},
                {"name": "candidate", "model": "y"},
            ],
            "baseline_variant": "does-not-exist",
        },
    )
    assert resp.status_code == 422
    assert "baseline" in resp.json()["detail"].lower()


def test_experiment_response_format_preserved() -> None:
    headers, _, project_id = _bootstrap()
    rubric_id, dataset_id = _bootstrap_experiment_pieces(headers, project_id)

    experiment = client.post(
        f"/v1/projects/{project_id}/experiments",
        headers=headers,
        json={
            "name": "shape-check",
            "dataset_id": dataset_id,
            "rubric_id": rubric_id,
            "variants": [
                {"name": "alpha", "model": "m1"},
                {"name": "beta", "model": "m2"},
            ],
            "baseline_variant": "alpha",
            "pass_criteria": {"min_pass_rate": 0.0},
        },
    )
    assert experiment.status_code == 201
    experiment_id = experiment.json()["id"]

    run = client.post(
        f"/v1/experiments/{experiment_id}/run",
        headers=headers,
        json={"triggered_by": "api"},
    )
    assert run.status_code == 202
    run_id = run.json()["run_id"]

    detail = client.get(
        f"/v1/experiments/{experiment_id}/runs/{run_id}", headers=headers
    )
    run_data = detail.json()["run"]
    for key in ("by_variant", "comparisons", "criteria_failures", "run_metadata"):
        assert key in run_data
    for variant_name in ("alpha", "beta"):
        bv = run_data["by_variant"][variant_name]
        for metric in (
            "pass_rate",
            "avg_score",
            "avg_latency_ms",
            "total_cost_usd",
            "avg_cost_usd_per_item",
            "total_items",
        ):
            assert metric in bv
    assert "beta_vs_alpha" in run_data["comparisons"]
    cmp_ = run_data["comparisons"]["beta_vs_alpha"]
    for k in ("delta_pass_rate", "delta_cost", "regression"):
        assert k in cmp_


def test_invalid_prompt_version_ref_marks_run_as_error() -> None:
    headers, _, project_id = _bootstrap()
    rubric_id, dataset_id = _bootstrap_experiment_pieces(headers, project_id)

    experiment = client.post(
        f"/v1/projects/{project_id}/experiments",
        headers=headers,
        json={
            "name": "bad-prompt-ref",
            "dataset_id": dataset_id,
            "rubric_id": rubric_id,
            "variants": [
                {"name": "control", "prompt_version_ref": "no-such-prompt@1"},
                {"name": "candidate", "model": "m"},
            ],
            "baseline_variant": "control",
        },
    )
    assert experiment.status_code == 201
    experiment_id = experiment.json()["id"]

    run = client.post(
        f"/v1/experiments/{experiment_id}/run",
        headers=headers,
        json={"triggered_by": "api"},
    )
    assert run.status_code == 202
    detail = client.get(
        f"/v1/experiments/{experiment_id}/runs/{run.json()['run_id']}",
        headers=headers,
    )
    run_data = detail.json()["run"]
    assert run_data["status"] == "error"
    assert "prompt_version_ref_invalid" in run_data["run_metadata"]["error"]


def _ingest_one(api_key: str, client_trace_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "traces": [
            {
                "client_trace_id": client_trace_id,
                "name": f"docops.{client_trace_id}",
                "environment": "prod",
                "started_at": now.isoformat(),
                "ended_at": (now + timedelta(milliseconds=10)).isoformat(),
                "status": "ok",
                "tags": {},
                "spans": [
                    {
                        "client_span_id": "cs_root",
                        "type": "llm_call",
                        "name": "openai.chat.completions",
                        "started_at": now.isoformat(),
                        "ended_at": (now + timedelta(milliseconds=5)).isoformat(),
                        "status": "ok",
                        "provider": "openai",
                        "model": "gpt-4o-mini",
                        "messages_in": [{"role": "user", "content": "hi"}],
                        "messages_out": [{"role": "assistant", "content": "yo"}],
                    }
                ],
            }
        ]
    }
    resp = client.post("/v1/traces", headers={"X-EvalOps-Key": api_key}, json=payload)
    assert resp.status_code == 202, resp.text
    return resp.json()["results"][0]["trace_id"]


def test_build_dataset_from_traces_ignores_soft_deleted() -> None:
    headers, _, project_id = _bootstrap()
    api_key = _create_api_key(headers, project_id)
    keep = _ingest_one(api_key, "ct_keep")
    drop = _ingest_one(api_key, "ct_drop")
    assert client.delete(f"/v1/traces/{drop}", headers=headers).status_code == 204

    dataset = client.post(
        f"/v1/projects/{project_id}/datasets",
        headers=headers,
        json={"slug": "trace-replay", "description": "Replay", "source": "traces"},
    )
    assert dataset.status_code == 201
    dataset_id = dataset.json()["id"]

    built = client.post(
        f"/v1/datasets/{dataset_id}/build-from-traces",
        headers=headers,
        json={"environment": "prod", "limit": 10},
    )
    assert built.status_code == 202, built.text
    assert built.json()["created"] == 1, "only the active trace must be ingested"

    items = client.get(f"/v1/datasets/{dataset_id}/items", headers=headers)
    assert items.status_code == 200
    names = [it["input"]["trace"]["name"] for it in items.json()["data"]]
    assert "docops.ct_keep" in names
    assert "docops.ct_drop" not in names


# ── Fix-7B.5 (A-08): experiments using llm_judge respect the judge budget ────

_JUDGE_EXP_RUBRIC = """
slug: exp-judge
name: Exp Judge
description: experiment rubric using llm_judge
threshold: 0.0
aggregate: mean
evaluators:
  - id: judge
    type: llm_judge
    weight: 1.0
    config:
      model: openai/gpt-4o-mini
      prompt: "Rate: {{ trace.output.assistant_message }}"
      pass_threshold: 0.5
      cost_cap_usd: 1.0
"""

_NONJUDGE_EXP_RUBRIC = """
slug: exp-nonjudge
name: Exp NonJudge
description: experiment rubric without llm_judge
threshold: 0.0
aggregate: mean
evaluators:
  - id: length_check
    type: length_bounds
    weight: 1.0
    config:
      target: trace.output.assistant_message
      unit: chars
      min: 1
      max: 5000
"""


def _build_experiment(headers, project_id, rubric_yaml) -> str:
    api_key = _create_api_key(headers, project_id)
    _ingest_trace(api_key)
    rubric_id = client.post(
        f"/v1/projects/{project_id}/rubrics",
        headers=headers, json={"yaml_source": rubric_yaml},
    ).json()["rubric"]["id"]
    dataset_id = client.post(
        f"/v1/projects/{project_id}/datasets",
        headers=headers,
        json={"slug": "replay", "description": "replay", "source": "traces"},
    ).json()["id"]
    client.post(
        f"/v1/datasets/{dataset_id}/build-from-traces",
        headers=headers, json={"environment": "prod", "limit": 10},
    )
    return client.post(
        f"/v1/projects/{project_id}/experiments",
        headers=headers,
        json={
            "name": "exp",
            "dataset_id": dataset_id,
            "rubric_id": rubric_id,
            "variants": [{"name": "control", "model": "openai/gpt-4o-mini", "params": {}}],
            "baseline_variant": "control",
        },
    ).json()["id"]


def _exhaust_judge_budget(headers, org_id, project_id) -> None:
    """Force a Subscription, tighten plan judge budget, seed monthly spend."""
    client.get(f"/v1/organizations/{org_id}/subscription", headers=headers)
    from app.models import EvaluationRun, Plan, Rubric, Subscription, Trace
    from app.security import new_id
    with SessionLocal() as db:
        sub = db.query(Subscription).filter(Subscription.organization_id == org_id).one()
        plan = db.get(Plan, sub.plan_id)
        plan.monthly_judge_budget_usd = 0.001
        db.add(plan)
        trace = db.query(Trace).filter(Trace.project_id == project_id).first()
        rubric = db.query(Rubric).filter(Rubric.project_id == project_id).first()
        db.add(EvaluationRun(
            id=new_id("evr"), project_id=project_id, trace_id=trace.id,
            rubric_id=rubric.id, rubric_version=999, triggered_by="seed",
            status="completed", cost_usd=0.10, run_metadata={},
        ))
        db.commit()


def test_experiment_with_llm_judge_blocked_when_budget_exhausted(monkeypatch) -> None:
    import app.domain.evaluators.llm_judge as lj_mod
    monkeypatch.setattr(lj_mod, "call_llm", lambda *a, **kw: '{"score": 0.9}')

    headers, org_id, project_id = _bootstrap()
    experiment_id = _build_experiment(headers, project_id, _JUDGE_EXP_RUBRIC)
    _exhaust_judge_budget(headers, org_id, project_id)

    resp = client.post(
        f"/v1/experiments/{experiment_id}/run",
        headers=headers, json={"triggered_by": "api"},
    )
    assert resp.status_code == 402, resp.text
    detail = resp.json()["detail"]
    assert detail["error"] == "judge_budget_exhausted"
    blob = str(detail)
    for leak in ("Traceback", "SELECT", "sqlite", "/home/", "Bearer"):
        assert leak not in blob


def test_experiment_without_llm_judge_not_blocked_by_judge_budget() -> None:
    headers, org_id, project_id = _bootstrap()
    experiment_id = _build_experiment(headers, project_id, _NONJUDGE_EXP_RUBRIC)
    _exhaust_judge_budget(headers, org_id, project_id)

    resp = client.post(
        f"/v1/experiments/{experiment_id}/run",
        headers=headers, json={"triggered_by": "api"},
    )
    assert resp.status_code == 202, resp.text
    assert resp.json()["status"] in ("completed", "error")


def test_experiment_with_llm_judge_runs_when_budget_available(monkeypatch) -> None:
    import app.domain.evaluators.llm_judge as lj_mod
    monkeypatch.setattr(lj_mod, "call_llm", lambda *a, **kw: '{"score": 0.9}')

    headers, org_id, project_id = _bootstrap()
    experiment_id = _build_experiment(headers, project_id, _JUDGE_EXP_RUBRIC)
    client.get(f"/v1/organizations/{org_id}/subscription", headers=headers)

    resp = client.post(
        f"/v1/experiments/{experiment_id}/run",
        headers=headers, json={"triggered_by": "api"},
    )
    assert resp.status_code == 202, resp.text
    assert resp.json()["status"] == "completed"
