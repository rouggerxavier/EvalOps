"""R1 access-control contract: reviewed route inventory plus real HTTP denials."""
import csv
import inspect
import json
import subprocess
import sys
from pathlib import Path

import jwt
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import event, select

from app.db import Base, SessionLocal, engine
from app.deps import ensure_org_membership
from app.main import app
from app.models import (
    ApiKey, Dataset, EvaluationRun, EvaluationSamplingJob, Experiment, ExperimentRun, ExportJob,
    Membership, Organization, Project, Prompt, PromptVersion, Rubric, RubricVersion,
    Trace, User, utcnow,
)
from app.security import (
    JWT_ALGORITHM, JWT_SECRET, create_access_token, generate_api_key, hash_api_key,
)

with (Path(__file__).parent / "fixtures/r1_route_permissions.tsv").open() as fixture:
    ROUTES = list(csv.DictReader(fixture, delimiter="\t"))
ORG_ROUTES = [r for r in ROUTES if r["permission"] != "own-contract"]
PERMISSIONS = {
    "owner": {"read", "write", "admin", "destructive"},
    "member": {"read", "write"}, "viewer": {"read"}, "legacy": set(), "outsider": set(),
}
IDS = {
    "org_id": "org", "project_id": "project", "trace_id": "trace",
    "rubric_id": "rubric", "prompt_id": "prompt", "dataset_id": "dataset",
    "experiment_id": "experiment", "export_id": "export", "key_id": "key",
    "version_num": "1", "run_id": "run", "client_trace_id": "client",
}
BODIES = {
    ("POST", "/v1/projects"): {"organization_id": "org", "name": "New project", "slug": "new-project"},
    ("PATCH", "/v1/projects/{project_id}"): {"name": "Changed"},
    ("POST", "/v1/projects/{project_id}/api-keys"): {"name": "New key", "environment": "prod"},
    ("POST", "/v1/projects/{project_id}/notifications/mark-read"): {"ids": ["notification"]},
    ("POST", "/v1/traces"): {"traces": []},
    ("POST", "/v1/projects/{project_id}/rubrics"): {"yaml_source": "unused"},
    ("POST", "/v1/rubrics/{rubric_id}/versions"): {"yaml_source": "unused"},
    ("POST", "/v1/evaluations/run"): {"trace_id": "trace", "rubric_id": "rubric"},
    ("POST", "/v1/projects/{project_id}/evaluations/batch"): {"rubric_id": "rubric"},
    ("POST", "/v1/projects/{project_id}/prompts"): {"slug": "new-prompt", "template": "hello"},
    ("POST", "/v1/prompts/{prompt_id}/versions"): {"template": "hello"},
    ("POST", "/v1/projects/{project_id}/datasets"): {"slug": "new-dataset"},
    ("POST", "/v1/datasets/{dataset_id}/items"): {"items": [{"input": {}}]},
    ("POST", "/v1/projects/{project_id}/experiments"): {
        "name": "New experiment", "dataset_id": "dataset", "rubric_id": "rubric", "variants": [{"name": "baseline"}],
    },
    ("POST", "/v1/traces/{trace_id}/feedback"): {"comment": "feedback"},
    ("POST", "/v1/traces/by-client-id/{client_trace_id}/feedback"): {"comment": "feedback"},
    ("POST", "/v1/exports"): {"project_id": "project"},
    ("POST", "/v1/traces/{trace_id}/flags"): {"reason": "manual"},
    ("POST", "/v1/traces/bulk-flag"): {"reason": "manual", "trace_ids": ["trace", "trace2"]},
    ("POST", "/v1/traces/compare"): {"left_trace_id": "trace", "right_trace_id": "trace2"},
}
PARAMS = {
    "/v1/resolve": {"org_slug": "org", "project_slug": "project"},
    "/v1/projects": {"organization_id": "org"},
    "/v1/traces": {"project_id": "project"},
    "/v1/analytics/overview": {"project_id": "project"},
}


def _headers(role):
    token = create_access_token(sub=role, email=f"{role}@example.com", name=role)
    # Even a validly signed owner claim must never override the database.
    claims = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    claims["role"] = "owner"
    return {"Authorization": f"Bearer {jwt.encode(claims, JWT_SECRET, algorithm=JWT_ALGORITHM)}"}


@pytest.fixture
def workspace(fake_arq_pool):
    fake_arq_pool.jobs.clear()
    with SessionLocal() as db:
        db.add(Organization(id="org", name="Org", slug="org"))
        db.add(Project(id="project", organization_id="org", name="Project", slug="project"))
        for role in PERMISSIONS:
            db.add(User(id=role, email=f"{role}@example.com", name=role))
            if role != "outsider":
                db.add(Membership(user_id=role, organization_id="org", role=role))
        for trace_id in ("trace", "trace2"):
            db.add(Trace(id=trace_id, project_id="project", organization_id="org", client_trace_id="client" if trace_id == "trace" else None,
                         name="Trace", environment="prod", status="ok", started_at=utcnow(), ended_at=utcnow(), duration_ms=10))
        db.add(Rubric(id="rubric", project_id="project", slug="rubric"))
        db.add(RubricVersion(id="rv", rubric_id="rubric", version=1, yaml_source="", parsed_spec={"evaluators": []}, created_by="owner"))
        db.add(Prompt(id="prompt", project_id="project", slug="prompt"))
        db.add(PromptVersion(id="pv", prompt_id="prompt", version=1, template="hello", created_by="owner"))
        db.add(Dataset(id="dataset", project_id="project", slug="dataset"))
        db.add(Experiment(id="experiment", project_id="project", name="Experiment", dataset_id="dataset", rubric_id="rubric"))
        db.add(ExperimentRun(id="run", project_id="project", experiment_id="experiment"))
        db.add(EvaluationRun(id="run", project_id="project", trace_id="trace", rubric_id="rubric", rubric_version=1, triggered_by="test", status="completed"))
        db.add(ExportJob(id="export", project_id="project"))
        db.add(EvaluationSamplingJob(trace_id="trace", project_id="project", rubric_id="rubric", rubric_version=1, status="blocked"))
        keys = {}
        for scope in ("read", "ingest", "evaluate"):
            raw, prefix = generate_api_key("prod")
            keys[scope] = {"X-EvalOps-Key": raw}
            db.add(ApiKey(id=scope, project_id="project", prefix=prefix, hash=hash_api_key(raw), name=scope, environment="prod", scopes=scope))
        db.commit()
    return TestClient(app), keys, fake_arq_pool


def _request(client, route, headers):
    method, path = route["method"], route["path"]
    kwargs = {"headers": headers, "params": PARAMS.get(path, {}) if method == "GET" else {}}
    if method in {"POST", "PUT", "PATCH"}:
        kwargs["json"] = BODIES.get((method, path), {})
    return client.request(method, path.format(**IDS), **kwargs)


def _snapshot():
    with SessionLocal() as db:
        return {table.name: db.execute(select(table).order_by(*table.primary_key.columns)).all()
                for table in Base.metadata.sorted_tables}


def _http_routes(application):
    routes = set()
    docs = {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}
    for registered in application.routes:
        # FastAPI supports both materialized APIRoutes and lazy included routers.
        contexts = registered.effective_route_contexts() if hasattr(registered, "effective_route_contexts") else [registered]
        for route in contexts:
            if route.path not in docs:
                routes.update((method, route.path) for method in route.methods)
    return routes


def test_inventory_discovers_even_routes_hidden_from_openapi():
    application = FastAPI()
    application.add_api_route("/v1/unclassified", lambda: None, methods=["POST"], include_in_schema=False)
    assert ("POST", "/v1/unclassified") in _http_routes(application)


def test_every_http_route_has_a_reviewed_permission_and_auth_contract():
    # Other suites register test-only routes during collection; inspect a clean real app.
    script = "import json\nfrom app.main import app\n" + inspect.getsource(_http_routes)
    script += "\nprint(json.dumps(sorted(_http_routes(app))))"
    result = subprocess.run([sys.executable, "-c", script], check=True, capture_output=True, text=True)
    actual = {tuple(route) for route in json.loads(result.stdout)}
    expected = {(r["method"], r["path"]) for r in ROUTES}
    assert len(expected) == len(ROUTES)
    assert actual == expected, "Classify every added HTTP method/path in r1_route_permissions.tsv"
    assert {(r["method"], r["path"]) for r in ROUTES if r["permission"] == "own-contract"} == {
        ("POST", "/v1/auth/register"), ("POST", "/v1/auth/login"),
        ("POST", "/v1/auth/change-password"), ("POST", "/v1/auth/logout"), ("GET", "/v1/auth/session"),
        ("GET", "/v1/me"), ("GET", "/v1/organizations"), ("POST", "/v1/organizations"),
        ("GET", "/v1/judges/cli"), ("GET", "/health/liveness"), ("GET", "/health/readiness"),
    }
    assert {r["permission"] for r in ROUTES} <= {"read", "write", "admin", "destructive", "own-contract"}


@pytest.mark.parametrize("role", PERMISSIONS)
def test_all_organizational_routes_deny_missing_permissions_without_effects(workspace, role, monkeypatch, no_dml):
    client, _, pool = workspace
    def unexpected_effect(*args, **kwargs):
        pytest.fail("Denied request reached a provider, export or cost-reservation boundary")
    for target in (
        "app.api.routes_evaluations.evaluate_trace", "app.api.routes_phase5.execute_experiment",
        "app.api.routes_trace_actions.get_or_create_counter", "app.api.routes_trace_actions.book_replay_cost",
        "app.api.routes_phase6.create_jsonl_export",
    ):
        monkeypatch.setattr(target, unexpected_effect)
    before = _snapshot()
    for route in ORG_ROUTES:
        if route["api_key"].startswith("only:") or route["permission"] in PERMISSIONS[role]:
            continue
        response = _request(client, route, _headers(role))
        expected = 404 if role == "outsider" else 403
        assert response.status_code == expected, (role, route, response.text)
        assert response.json() == {"detail": "not_found" if expected == 404 else "forbidden"}
    assert _snapshot() == before, "Denied requests must not modify rows, costs, keys or jobs"
    assert pool.jobs == []
    assert no_dml == []


@pytest.mark.parametrize("role", ["owner", "member", "viewer"])
def test_all_read_routes_allow_known_memberships(workspace, role):
    client, _, _ = workspace
    before = _snapshot()
    for route in ORG_ROUTES:
        if route["permission"] != "read":
            continue
        response = _request(client, route, _headers(role))
        expected = 409 if route["path"].endswith("/download") else 200
        assert response.status_code == expected, (role, route, response.text)
    assert _snapshot() == before, "Read requests must not create configuration/counters (#30)"


@pytest.mark.parametrize("scope", ["read", "ingest", "evaluate"])
def test_every_route_preserves_api_key_scope_or_jwt_only_contract(workspace, scope):
    client, keys, pool = workspace
    for route in ORG_ROUTES:
        required = route["api_key"].removeprefix("only:")
        # Successful mutations have their own cases; this loop proves no new key access.
        if required == scope and route["permission"] != "read":
            continue
        before = _snapshot() if required != scope else None
        response = _request(client, route, keys[scope])
        if before is not None:
            assert _snapshot() == before, (scope, route, "denied key request changed rows")
        expected = 401 if required == "jwt" else 200 if required == scope else 403
        assert response.status_code == expected, (scope, route, response.text)
    assert pool.jobs == []


@pytest.mark.parametrize("role", PERMISSIONS)
@pytest.mark.parametrize("permission", ["read", "write", "admin", "destructive", "typo"])
def test_membership_permission_matrix_uses_literal_db_roles(workspace, role, permission):
    with SessionLocal() as db:
        if permission in PERMISSIONS[role]:
            assert ensure_org_membership(db, role, "org", permission).role == role
        else:
            with pytest.raises(HTTPException) as exc:
                ensure_org_membership(db, role, "org", permission)
            assert exc.value.status_code == (404 if role == "outsider" else 403)


@pytest.mark.parametrize("role", ["owner", "member"])
def test_operational_writes_remain_available(workspace, role):
    client, _, pool = workspace
    headers = _headers(role)
    assert client.post("/v1/projects/project/prompts", headers=headers, json={"slug": "created", "template": "Hi"}).status_code == 201
    assert client.post("/v1/traces/trace/flags", headers=headers, json={"reason": "manual"}).status_code == 201
    assert client.post("/v1/projects/project/evaluations/batch", headers=headers, json={"rubric_id": "rubric", "trace_ids": ["trace2"]}).status_code == 202
    assert len(pool.jobs) == 1


def test_demoting_membership_blocks_next_request_with_same_jwt(workspace):
    client, _, pool = workspace
    headers = _headers("owner")
    response = client.post("/v1/projects/project/evaluations/batch", headers=headers, json={"rubric_id": "rubric", "trace_ids": ["trace2"]})
    assert response.status_code == 202
    queued = list(pool.jobs)
    with SessionLocal() as db:
        db.get(Membership, ("owner", "org")).role = "viewer"
        db.commit()
    before = _snapshot()
    assert client.post("/v1/projects/project/evaluations/batch", headers=headers, json={"rubric_id": "rubric"}).status_code == 403
    assert client.get("/v1/projects/project/api-keys", headers=headers).status_code == 403
    assert pool.jobs == queued
    assert _snapshot() == before


def test_sampling_evaluate_key_keeps_its_capability_without_a_membership(workspace):
    client, keys, _ = workspace
    assert client.put("/v1/projects/project/evaluation-sampling", headers=keys["evaluate"], json={}).status_code == 200
    assert client.post("/v1/projects/project/evaluations/batch", headers=keys["evaluate"], json={"rubric_id": "rubric", "trace_ids": ["trace2"]}).status_code == 202
    assert client.post("/v1/traces/trace/feedback", headers=keys["ingest"], json={"comment": "sdk"}).status_code == 201
    assert client.post("/v1/traces", headers=keys["ingest"], json={"traces": []}).status_code == 202


@pytest.fixture
def no_dml():
    statements = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().split(" ", 1)[0].upper() in {"INSERT", "UPDATE", "DELETE"}:
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", capture)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", capture)


@pytest.mark.parametrize("scope", ["ingest", "evaluate"])
def test_all_existing_api_key_mutations_remain_available(workspace, scope):
    client, keys, _ = workspace
    for route in ORG_ROUTES:
        if route["api_key"].removeprefix("only:") != scope or route["permission"] == "read":
            continue
        response = _request(client, route, keys[scope])
        assert response.status_code in {200, 201, 202}, (scope, route, response.text)


@pytest.mark.parametrize("endpoint,body", [
    ("/v1/traces/compare", {"left_trace_id": "trace", "right_trace_id": "foreign-trace"}),
    ("/v1/traces/bulk-flag", {"trace_ids": ["trace", "foreign-trace"], "reason": "manual"}),
    ("/v1/evaluations/run", {"trace_id": "trace", "rubric_id": "foreign-rubric"}),
    ("/v1/projects/project/experiments", {"name": "Experiment", "dataset_id": "foreign-dataset", "rubric_id": "rubric", "variants": [{"name": "baseline"}]}),
])
def test_json_secondary_resources_cannot_escape_tenant(workspace, endpoint, body):
    client, _, pool = workspace
    with SessionLocal() as db:
        db.add(Organization(id="foreign", name="Foreign", slug="foreign"))
        db.add(Project(id="foreign", organization_id="foreign", name="Foreign", slug="foreign"))
        db.add(Trace(id="foreign-trace", project_id="foreign", organization_id="foreign", name="Foreign", environment="prod", status="ok", started_at=utcnow(), ended_at=utcnow(), duration_ms=0))
        db.add(Rubric(id="foreign-rubric", project_id="foreign", slug="foreign"))
        db.add(Dataset(id="foreign-dataset", project_id="foreign", slug="foreign"))
        db.commit()
    before = _snapshot()
    response = client.post(endpoint, headers=_headers("owner"), json=body)
    assert response.status_code == 404, response.text
    assert _snapshot() == before
    assert pool.jobs == []


def test_legacy_role_remains_stored_and_visible_to_owner(workspace):
    client, _, _ = workspace
    response = client.get("/v1/organizations/org/members", headers=_headers("owner"))
    assert next(row for row in response.json()["data"] if row["user_id"] == "legacy")["role"] == "legacy"
    assert client.get("/v1/me", headers=_headers("legacy")).status_code == 200
    assert client.get("/v1/organizations", headers=_headers("legacy")).status_code == 200
    with SessionLocal() as db:
        assert db.get(Membership, ("legacy", "org")).role == "legacy"


@pytest.mark.parametrize("secondary_role", ["viewer", "legacy", "outsider"])
@pytest.mark.parametrize("operation", ["compare-left", "compare-right", "bulk-first", "bulk-last", "evaluation", "experiment"])
def test_each_secondary_resource_checks_its_own_membership_before_effects(
    workspace, secondary_role, operation, no_dml, monkeypatch,
):
    client, _, pool = workspace
    with SessionLocal() as db:
        db.add(Organization(id="secondary", name="Secondary", slug="secondary"))
        db.add(Project(id="secondary", organization_id="secondary", name="Secondary", slug="secondary"))
        if secondary_role != "outsider":
            db.add(Membership(user_id="owner", organization_id="secondary", role=secondary_role))
        db.add(Trace(id="secondary-trace", project_id="secondary", organization_id="secondary", name="Secondary",
                     environment="prod", status="ok", started_at=utcnow(), ended_at=utcnow(), duration_ms=0))
        db.add(Rubric(id="secondary-rubric", project_id="secondary", slug="secondary"))
        db.add(Dataset(id="secondary-dataset", project_id="secondary", slug="secondary"))
        db.commit()
    no_dml.clear()

    def unexpected_effect(*args, **kwargs):
        pytest.fail("Secondary resource authorization must precede evaluation or reservation")

    monkeypatch.setattr("app.api.routes_evaluations.evaluate_trace", unexpected_effect)
    monkeypatch.setattr("app.api.routes_phase5.execute_experiment", unexpected_effect)
    requests = {
        "compare-left": ("/v1/traces/compare", {"left_trace_id": "secondary-trace", "right_trace_id": "trace"}),
        "compare-right": ("/v1/traces/compare", {"left_trace_id": "trace", "right_trace_id": "secondary-trace"}),
        "bulk-first": ("/v1/traces/bulk-flag", {"trace_ids": ["secondary-trace", "trace"], "reason": "manual"}),
        "bulk-last": ("/v1/traces/bulk-flag", {"trace_ids": ["trace", "secondary-trace"], "reason": "manual"}),
        "evaluation": ("/v1/evaluations/run", {"trace_id": "trace", "rubric_id": "secondary-rubric"}),
        "experiment": ("/v1/projects/project/experiments", {
            "name": "Secondary", "dataset_id": "secondary-dataset", "rubric_id": "rubric", "variants": [{"name": "baseline"}],
        }),
    }
    endpoint, body = requests[operation]
    before = _snapshot()
    response = client.post(endpoint, headers=_headers("owner"), json=body)
    expected = 404 if secondary_role == "outsider" else 403
    if operation.startswith("compare") and secondary_role == "viewer":
        expected = 400  # Both reads are authorized; comparing different projects is invalid.
    assert response.status_code == expected, response.text
    assert _snapshot() == before
    assert no_dml == []
    assert pool.jobs == []


@pytest.mark.parametrize("stored_role", ["Owner", "OWNER", " owner ", "admin", ""])
def test_nonliteral_roles_are_not_normalized_or_promoted(workspace, stored_role):
    client, _, _ = workspace
    with SessionLocal() as db:
        db.get(Membership, ("owner", "org")).role = stored_role
        db.commit()
    before = _snapshot()
    response = client.get("/v1/traces/trace", headers=_headers("owner"))
    assert response.status_code == 403
    assert _snapshot() == before
