from datetime import timedelta
import uuid

from fastapi.testclient import TestClient
import pytest

from app.db import Base, SessionLocal, engine
from app.main import app
from app import models as m
from app.security import create_access_token

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


def bootstrap():
    with SessionLocal() as db:
        db.add(m.User(id="user", email="user@example.com", name="User"))
        db.commit()
    headers = {"Authorization": "Bearer " + create_access_token(sub="user", email="user@example.com", name="User")}
    org = client.post("/v1/organizations", headers=headers, json={"name": "Org", "slug": "org"}).json()
    project = client.post("/v1/projects", headers=headers, json={"organization_id": org["id"], "name": "Test", "slug": "test"}).json()
    return headers, project["id"], org["id"]


def post(path, body, headers, key=None, expected=201):
    response = client.post("/v1" + path, headers={**headers, "Idempotency-Key": key or str(uuid.uuid4())}, json=body)
    assert response.status_code == expected, response.text
    return response.json()


def fixture(headers, project, env="dev"):
    dataset = post(f"/projects/{project}/datasets", {"slug": "prices", "task_type": "regression",
        "task_schema": {"target": {"name": "price", "unit": "BRL"}}, "access": {"environment": env},
        "items": [{"sample_id": f"s{i}", "input": {"x": i}, "expected_output": {"value": i}} for i in range(1,4)]}, headers)
    snap = post(f"/datasets/{dataset['id']}/snapshots", {"environment": env}, headers)
    model = post(f"/projects/{project}/model-versions", {"model": {"name": "linear", "version_ref": "v1"}, "access": {"environment": env}}, headers)
    predictions = post(f"/projects/{project}/prediction-sets", {"snapshot_id": snap["id"], "model_version_id": model["id"],
        "environment": env, "rows": [{"sample_id": f"s{i}", "prediction": {"value": value}} for i,value in enumerate([1,2,5],1)]}, headers)
    return dataset, snap, model, predictions


def key_for(headers, project, scopes=("read", "write", "evaluate"), env="dev"):
    principal = post(f"/projects/{project}/service-principals", {"name": "Agent"}, headers)
    result = post(f"/projects/{project}/api-keys", {"name": "Agent key", "environment": env,
        "service_principal_id": principal["id"], "scopes": list(scopes), "expires_at": (m.utcnow()+timedelta(days=1)).isoformat()}, headers)
    return {"X-EvalOps-Key": result["key"]}, principal, result


def test_vertical_and_immutable_snapshot_idempotency():
    headers, project, _ = bootstrap()
    dataset, snap, model, predictions = fixture(headers, project)
    body = {"prediction_set_id": predictions["id"]}
    first = post(f"/projects/{project}/task-evaluations", body, headers, key="repeat")
    assert post(f"/projects/{project}/task-evaluations", body, headers, key="repeat") == first
    assert first["decision"] == "inconclusive" and "passed" not in first
    facts = client.get(first["links"]["metrics"], headers=headers).json()["data"]
    mae = next(f for f in facts if f["definition_id"] == "regression.mae")
    assert mae["value"] == pytest.approx(2/3) and mae["n_valid"] == 3
    with SessionLocal() as db:
        item = db.query(m.DatasetItem).filter_by(dataset_id=dataset["id"]).first()
        item.expected_output = {"value": 900}
        db.commit()
    again = client.get(f"/v1/dataset-snapshots/{snap['id']}", headers=headers).json()
    assert again["content_hash"] == snap["content_hash"]
    assert client.get(f"/v1/task-evaluations/{first['id']}", headers=headers).json()["id"] == first["id"]
    changed = {"model": {"name": "linear", "version_ref": "v1", "config": {"changed": True}}, "access": {"environment": "dev"}}
    post(f"/projects/{project}/model-versions", changed, headers, expected=409)


def test_principal_environment_scope_and_revocation():
    headers, project, _ = bootstrap()
    _, snap, _, predictions = fixture(headers, project, "prod")
    key, principal, raw = key_for(headers, project)
    assert client.get(f"/v1/dataset-snapshots/{snap['id']}", headers=key).status_code == 404
    assert client.get(f"/v1/projects/{project}/model-versions", headers=key).json()["data"] == []
    post(f"/projects/{project}/task-evaluations", {"prediction_set_id": predictions["id"]}, key, expected=404)
    assert client.get(f"/v1/projects/{project}/traces", headers=key).status_code == 404
    assert client.get(f"/v1/projects/{project}/service-principals", headers=key).status_code == 403
    assert client.get(f"/v1/projects/{project}/capabilities", headers=key).status_code == 200
    assert client.post(f"/v1/service-principals/{principal['id']}/disable", headers=headers).status_code == 200
    assert client.get(f"/v1/projects/{project}/capabilities", headers=key).status_code == 401


def test_transitive_restriction_denies_derived_metrics():
    headers, project, _ = bootstrap()
    dataset, snap, _, predictions = fixture(headers, project)
    result = post(f"/projects/{project}/task-evaluations", {"prediction_set_id": predictions["id"]}, headers)
    key, _, _ = key_for(headers, project)
    assert client.get(result["links"]["metrics"], headers=key).status_code == 200
    # Restrict the source to a non-overlapping environment by first using a neutral owner-created source.
    with SessionLocal() as db:
        row = db.get(m.Dataset, dataset["id"])
        row.access_label = {**row.access_label, "allowed_environments": ["prod"], "access_revision": 2}
        db.commit()
    assert client.get(result["links"]["metrics"], headers=key).status_code == 404
    assert client.get(f"/v1/dataset-snapshots/{snap['id']}", headers=key).status_code == 404
    assert client.get(f"/v1/projects/{project}/task-evaluations", headers=key).json()["data"] == []


def test_atomic_import_and_legacy_key_denial():
    headers, project, _ = bootstrap()
    _, snap, model, _ = fixture(headers, project)
    with SessionLocal() as db:
        before = db.query(m.PredictionSet).count()
    body = {"snapshot_id": snap["id"], "model_version_id": model["id"], "environment": "dev", "rows": [{"sample_id": "unknown", "prediction": {"value": 1}}]}
    post(f"/projects/{project}/prediction-sets", body, headers, expected=422)
    with SessionLocal() as db:
        assert db.query(m.PredictionSet).count() == before
    key = post(f"/projects/{project}/api-keys", {"name": "Legacy", "environment": "dev", "scopes": ["read"]}, headers)
    assert client.get(f"/v1/dataset-snapshots/{snap['id']}", headers={"X-EvalOps-Key": key["key"]}).status_code == 403


def test_database_guards_and_cross_project_foreign_keys():
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError
    headers, project, org = bootstrap()
    _, snap, model, predictions = fixture(headers, project)
    with SessionLocal() as db:
        with pytest.raises(IntegrityError, match="immutable_task_resource"):
            db.execute(text("UPDATE dataset_snapshots SET content='{}' WHERE id=:id"), {"id": snap["id"]})
            db.commit()
        db.rollback()
        db.add(m.Project(id="other", organization_id=org, name="Other", slug="other"))
        db.commit()
        db.execute(text("PRAGMA foreign_keys=ON"))
        assert db.execute(text("PRAGMA foreign_keys")).scalar() == 1
        db.add(m.PredictionSet(id="bad", project_id="other", snapshot_id=snap["id"], model_version_id=model["id"],
            environment="dev", content_hash="bad", producer_manifest={}, access_label={}))
        with pytest.raises(IntegrityError):
            db.commit()


def test_principal_can_create_own_environment_and_receipt_reauthorizes():
    headers, project, _ = bootstrap()
    key, principal, raw = key_for(headers, project)
    _, _, _, predictions = fixture(key, project)
    result = post(f"/projects/{project}/task-evaluations", {"prediction_set_id": predictions["id"]}, key, key="retry")
    assert client.get(result["links"]["metrics"], headers=key).status_code == 200
    assert client.post(f"/v1/projects/{project}/api-keys/{raw['id']}/revoke", headers=headers).status_code in (200, 204)
    post(f"/projects/{project}/task-evaluations", {"prediction_set_id": predictions["id"]}, key, key="retry", expected=401)


def test_sdk_reads_identical_facts_over_real_http():
    import json
    import sys
    from pathlib import Path
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "packages/sdk-python"))
    from evalops import Client
    headers, project, _ = bootstrap()
    key, _, _ = key_for(headers, project)
    _, _, _, predictions = fixture(headers, project)
    class Handler(BaseHTTPRequestHandler):
        def handle_request(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            response = client.request(self.command, self.path, headers=dict(self.headers), content=body)
            self.send_response(response.status_code)
            self.end_headers()
            self.wfile.write(response.content)
        do_GET = handle_request
        do_POST = handle_request
        do_PATCH = handle_request
        def log_message(self, *args):
            pass
    http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=http.serve_forever, daemon=True)
    thread.start()
    try:
        sdk = Client(api_key=key["X-EvalOps-Key"], api_url=f"http://127.0.0.1:{http.server_port}/v1")
        result = sdk.evaluate(project, predictions["id"], idempotency_key="sdk-evaluate")
        direct = client.get(f"/v1/task-evaluations/{result['id']}", headers=headers).json()
        assert sdk.task_result(result["id"]) == direct == result
        assert sdk.task_metrics(result["id"]) == client.get(result["links"]["metrics"], headers=headers).json()
        investigation = sdk.create_investigation(project, {"environment": "dev", "state": {"title": "SDK continuity", "run_ids": [result["id"]]}}, idempotency_key="sdk-investigation")
        revised = sdk.update_investigation(investigation["id"], {"title": "Next session", "next_steps": ["Review references"]}, revision=1, idempotency_key="sdk-revision")
        assert sdk.get_investigation(investigation["id"]) == revised
        assert len(sdk.investigation_history(investigation["id"])["data"]) == 2
    finally:
        http.shutdown()
        http.server_close()
        thread.join(timeout=2)


@pytest.mark.parametrize("count,offset,expected", [(3, 0, "inconclusive"), (30, 0.5, "pass"), (30, 2, "fail")])
def test_paired_comparison_and_legacy_view(count, offset, expected):
    headers, project, _ = bootstrap()
    dataset = post(f"/projects/{project}/datasets", {"slug": "paired", "task_type": "regression",
        "task_schema": {"target": {"name": "price", "unit": "BRL"}}, "access": {"environment": "dev"},
        "items": [{"sample_id": f"s{i}", "input": {}, "expected_output": {"value": i}} for i in range(1,count+1)]}, headers)
    snap = post(f"/datasets/{dataset['id']}/snapshots", {"environment": "dev"}, headers)
    evaluations, variants = [], []
    for name, error in (("baseline",1), ("candidate",offset)):
        model = post(f"/projects/{project}/model-versions", {"model": {"name": name, "version_ref": "v1"}, "access": {"environment": "dev"}}, headers)
        variants.append({"name": name, "model_version_id": model["id"]})
        predictions = post(f"/projects/{project}/prediction-sets", {"snapshot_id": snap["id"], "model_version_id": model["id"], "environment": "dev",
            "rows": [{"sample_id": f"s{i}", "prediction": {"value": i+error}} for i in reversed(range(1,count+1))]}, headers)
        evaluations.append(post(f"/projects/{project}/task-evaluations", {"prediction_set_id": predictions["id"]}, headers))
    experiment = post(f"/projects/{project}/experiments", {"kind": "task_comparison", "name": "Regression check", "dataset_id": dataset["id"],
        "snapshot_id": snap["id"], "environment": "dev", "variants": variants}, headers)
    result = post(f"/experiments/{experiment['id']}/comparisons", {"baseline_evaluation_id": evaluations[0]["id"], "candidate_evaluation_ids": [evaluations[1]["id"]]}, headers)["run"]
    assert result["decision"] == expected and "passed" not in result
    assert result["policy_timing"] == "post_observation"
    assert result["n_pairs"] == count
    assert client.get(f"/v1/experiments/{experiment['id']}/runs/{result['id']}", headers=headers).status_code == 409
    assert client.get(f"/v1/experiments/{experiment['id']}/runs/{result['id']}?view=task_v1", headers=headers).json()["run"] == result
    assert client.get(f"/v1/projects/{project}/experiments", headers=headers).json()["data"] == []
    assert client.get(f"/v1/projects/{project}/experiments?view=task_v1", headers=headers).json()["data"][0]["id"] == experiment["id"]
    with SessionLocal() as db:
        row = db.get(m.ExperimentRun, result["id"])
        assert row.passed is None and row.decision == expected


@pytest.mark.parametrize("role", ["viewer", "member", "outsider", "unknown"])
def test_new_route_inventory_denies_missing_roles_without_mutation(role):
    import csv
    from pathlib import Path
    from sqlalchemy import select
    headers, project, org = bootstrap()
    dataset, snap, model, predictions = fixture(headers, project)
    evaluation = post(f"/projects/{project}/task-evaluations", {"prediction_set_id": predictions["id"]}, headers)
    _, principal, _ = key_for(headers, project)
    item_id = None
    with SessionLocal() as db:
        item_id = db.query(m.DatasetItem).filter_by(dataset_id=dataset["id"]).first().id
        db.add(m.User(id="actor", email="actor@example.com", name="Actor"))
        if role != "outsider":
            db.add(m.Membership(user_id="actor", organization_id=org, role=role))
        db.commit()
    investigation = post(f"/projects/{project}/investigations", {"environment": "dev", "state": {"title": "Investigation"}}, headers)
    from test_execution_imports import payload as execution_payload
    imported_execution = post(f"/projects/{project}/execution-imports", execution_payload(snap, model, predictions), headers)
    with SessionLocal() as db:
        db.add(m.Trace(id="trace", project_id=project, organization_id=org, name="Trace", environment="dev", status="error", started_at=m.utcnow(), ended_at=m.utcnow(), duration_ms=0))
        db.commit()
    token = {"Authorization": "Bearer " + create_access_token(sub="actor", email="actor@example.com", name="Actor"), "Idempotency-Key": "denied"}
    ids = dict(project_id=project, dataset_id=dataset["id"], snapshot_id=snap["id"], model_id=model["id"],
               set_id=predictions["id"], evaluation_id=evaluation["id"], principal_id=principal["id"],
               resource_id=snap["id"], kind="snapshot", experiment_id="missing", item_id=item_id, investigation_id=investigation["id"], trace_id="trace", execution_id=imported_execution["id"])
    bodies = {
        "/v1/projects/{project_id}/execution-imports": execution_payload(snap, model, predictions),
        "/v1/projects/{project_id}/investigations": {"environment": "dev", "state": {"title": "Investigation"}},
        "/v1/investigations/{investigation_id}": {"state": {"title": "Changed"}},
        "/v1/task-resources/dataset/{dataset_id}/classify": {"environment": "dev"},
        "/v1/datasets/{dataset_id}/snapshots": {"environment": "dev"},
        "/v1/projects/{project_id}/model-versions": {"model": {"name": "x", "version_ref": "1"}, "access": {"environment": "dev"}},
        "/v1/projects/{project_id}/prediction-sets": {"snapshot_id": snap["id"], "model_version_id": model["id"], "environment": "dev", "rows": []},
        "/v1/projects/{project_id}/service-principals": {"name": "Agent"},
        "/v1/projects/{project_id}/task-datasets": {"slug": "new", "task_type": "regression", "task_schema": {"target": {"name": "y", "unit": "1"}}, "access": {"environment": "dev"}},
        "/v1/projects/{project_id}/task-evaluations": {"prediction_set_id": predictions["id"]},
        "/v1/experiments/{experiment_id}/comparisons": {"baseline_evaluation_id": evaluation["id"], "candidate_evaluation_ids": ["other"]},
        "/v1/task-resources/{kind}/{resource_id}/restrict": {"allowed_environments": ["dev"], "access_revision": 1},
        "/v1/datasets/{dataset_id}/cases": {"environment": "dev", "case": {"sample_id": "new", "input": {}}},
        "/v1/datasets/{dataset_id}/cases/{item_id}": {"case": {"sample_id": "s1", "input": {}}},
    }
    def state():
        with SessionLocal() as db:
            return {table.name: db.execute(select(table).order_by(*table.primary_key.columns)).all() for table in Base.metadata.sorted_tables}
    before = state()
    allowed = {"read"} if role == "viewer" else {"read", "write", "evaluate"} if role == "member" else set()
    with (Path(__file__).parent / "fixtures/task_route_permissions.tsv").open() as stream:
        for route in csv.DictReader(stream, delimiter="\t"):
            if route["permission"] in allowed:
                continue
            kwargs = {"headers": token}
            if route["method"] != "GET": kwargs["json"] = bodies.get(route["path"], {})
            response = client.request(route["method"], route["path"].format(**ids), **kwargs)
            assert response.status_code in ({404} if role == "outsider" or "experiments" in route["path"] else {403}), (route, response.text)
    assert state() == before


def test_neutral_owner_source_is_shared_only_explicitly_and_restriction_is_transitive():
    headers, project, _ = bootstrap()
    access = {"environment": "dev", "independent": True, "allowed_environments": ["dev","prod"],
              "justification": "Independent synthetic fixture", "evidence": "Synthetic construction v1"}
    dataset = post(f"/projects/{project}/datasets", {"slug": "shared", "task_type": "regression", "task_schema": {"target": {"name": "price", "unit": "BRL"}},
        "access": access, "items": [{"sample_id": "s1", "input": {}, "expected_output": {"value": 1}}]}, headers)
    snap = post(f"/datasets/{dataset['id']}/snapshots", {"environment": "dev", "allowed_environments": ["dev","prod"]}, headers)
    model = post(f"/projects/{project}/model-versions", {"model": {"name": "shared", "version_ref": "v1"}, "access": access}, headers)
    dev, _, _ = key_for(headers, project)
    prod, _, _ = key_for(headers, project, env="prod")
    for key in (dev, prod):
        assert client.get(f"/v1/dataset-snapshots/{snap['id']}", headers=key).status_code == 200
    predictions = post(f"/projects/{project}/prediction-sets", {"snapshot_id": snap["id"], "model_version_id": model["id"], "environment": "dev", "rows": []}, dev)
    body = {"prediction_set_id": predictions["id"]}
    evaluation = post(f"/projects/{project}/task-evaluations", body, dev, key="shared-evaluate")
    assert client.get(evaluation["links"]["metrics"], headers=prod).status_code == 404
    post(f"/task-resources/dataset/{dataset['id']}/restrict", {"allowed_environments": ["prod"], "access_revision": 1}, headers, expected=200)
    assert client.get(evaluation["links"]["metrics"], headers=dev).status_code == 404
    post(f"/projects/{project}/task-evaluations", body, dev, key="shared-evaluate", expected=404)
    assert client.get(f"/v1/dataset-snapshots/{snap['id']}", headers=prod).json()["content_hash"] == snap["content_hash"]


def test_case_revision_human_review_and_snapshot_freeze():
    headers, project, _ = bootstrap()
    dataset, old_snap, _, _ = fixture(headers, project)
    case = post(f"/datasets/{dataset['id']}/cases", {"environment": "dev", "case": {"sample_id": "review-me", "input": {}, "expected_output": {"value": 100}}}, headers)
    body = {"case": {"sample_id": "review-me", "input": {}, "expected_output": {"value": 100}, "reference_status": "reviewed"}, "review_reason": "Checked against the human reference"}
    key, _, _ = key_for(headers, project)
    path = f"/v1/datasets/{dataset['id']}/cases/{case['id']}"
    assert client.patch(path, headers={**key, "If-Match": "1", "Idempotency-Key": "case-patch"}, json=body).status_code == 403
    reviewed = client.patch(path, headers={**headers, "If-Match": "1", "Idempotency-Key": "case-patch"}, json=body)
    assert reviewed.status_code == 200 and reviewed.json()["revision"] == 2
    assert client.patch(path, headers={**headers, "If-Match": "1", "Idempotency-Key": "stale-case"}, json=body).status_code == 409
    new_snap = post(f"/datasets/{dataset['id']}/snapshots", {"environment": "dev"}, headers)
    assert new_snap["item_count"] == old_snap["item_count"] + 1
    items = client.get(f"/v1/dataset-snapshots/{new_snap['id']}/items", headers=headers).json()["data"]
    frozen = next(item for item in items if item["sample_id"] == "review-me")
    assert frozen["reference_status"] == "reviewed" and frozen["metadata"]["reference_review"]["actor_user_id"] == "user"
    assert client.get(f"/v1/dataset-snapshots/{old_snap['id']}", headers=headers).json()["content_hash"] == old_snap["content_hash"]


def test_histogram_config_is_frozen_and_samples_sort_by_stored_error():
    headers, project, _ = bootstrap()
    _, _, _, predictions = fixture(headers, project)
    result = post(f"/projects/{project}/task-evaluations", {"prediction_set_id": predictions["id"],
        "evaluator": {"id": "regression.standard", "version": "1", "config": {"histogram_edges": [-1,0,1]}}}, headers)
    metrics = client.get(result["links"]["metrics"], headers=headers).json()["data"]
    histogram = next(fact for fact in metrics if fact["definition_id"] == "regression.residual_histogram")
    assert histogram["value"]["cells"] == [[0],[0],[2],[1]]
    samples = client.get(result["links"]["samples"] + "?order=absolute_error_desc", headers=headers).json()["data"]
    assert samples[0]["sample_id"] == "s3" and samples[0]["residual"]["y"] == 2


def test_read_only_principal_and_cross_project_references_deny_without_writes():
    from sqlalchemy import select
    headers, project, org = bootstrap()
    _, snap, model, predictions = fixture(headers, project)
    key, _, _ = key_for(headers, project, scopes=("read",))
    with SessionLocal() as db:
        before = {table.name: db.execute(select(table).order_by(*table.primary_key.columns)).all() for table in Base.metadata.sorted_tables}
    post(f"/projects/{project}/task-evaluations", {"prediction_set_id": predictions["id"]}, key, expected=403)
    with SessionLocal() as db:
        after = {table.name: db.execute(select(table).order_by(*table.primary_key.columns)).all() for table in Base.metadata.sorted_tables}
    assert before == after
    other = post("/projects", {"organization_id": org, "name": "Other", "slug": "other"}, headers)
    foreign_model = post(f"/projects/{other['id']}/model-versions", {"model": {"name": "foreign", "version_ref": "v1"}, "access": {"environment": "dev"}}, headers)
    post(f"/projects/{project}/prediction-sets", {"snapshot_id": snap["id"], "model_version_id": foreign_model["id"], "environment": "dev", "rows": []}, headers, expected=404)


def test_nonfinite_case_json_is_a_structural_422():
    headers, project, _ = bootstrap()
    dataset, _, _, _ = fixture(headers, project)
    response = client.post(f"/v1/datasets/{dataset['id']}/cases", headers={**headers, "Content-Type": "application/json", "Idempotency-Key": "invalid"},
        content='{"environment":"dev","case":{"sample_id":"bad","input":{},"expected_output":{"value":NaN}}}')
    assert response.status_code == 422 and response.json()["detail"] == "invalid_task_payload"


def test_classification_api_shares_facts_and_rejects_task_mismatch():
    from test_classification import fixture as classification_fixture
    headers, project, _ = bootstrap()
    key, _, _ = key_for(headers, project)
    snapshot, rows = classification_fixture()
    dataset = post(f"/projects/{project}/datasets", {"slug": "classification", "task_type": "classification",
        "task_schema": snapshot.task_schema.model_dump(mode="json"), "access": {"environment": "dev"},
        "items": [item.model_dump(mode="json") for item in snapshot.items]}, key)
    snap = post(f"/datasets/{dataset['id']}/snapshots", {"environment": "dev"}, key)
    model = post(f"/projects/{project}/model-versions", {"model": {"name": "classifier", "version_ref": "v1", "task_type": "classification"}, "access": {"environment": "dev"}}, key)
    payload = {"snapshot_id": snap["id"], "model_version_id": model["id"], "environment": "dev", "rows": [row.model_dump(mode="json") for row in rows]}
    invalid = {**payload, "rows": [{"sample_id": "0", "prediction": {"label": "unknown"}}]}
    post(f"/projects/{project}/prediction-sets", invalid, key, expected=422)
    predictions = post(f"/projects/{project}/prediction-sets", payload, key)
    post(f"/projects/{project}/task-evaluations", {"prediction_set_id": predictions["id"]}, key, expected=422)
    result = post(f"/projects/{project}/task-evaluations", {"prediction_set_id": predictions["id"], "evaluator": {"id": "classification.standard"}}, key)
    path = f"/v1/task-evaluations/{result['id']}"
    assert client.get(path, headers=key).json() == client.get(path, headers=headers).json() == result
    metrics = client.get(path+"/metrics", headers=key).json()["data"]
    assert next(fact["value"] for fact in metrics if fact["definition_id"] == "classification.accuracy") == .5
    assert len({(fact["definition_id"], fact["scope"], fact["scope_key"]) for fact in metrics}) == len(metrics)
    samples = client.get(path+"/samples", headers=key).json()["data"]
    assert len(samples) == 4 and samples[0]["expected_output"] == {"label": "no"}
    assert [sample["correctness"]["y"] for sample in samples] == [1, 0, 1, 0]
    failures = client.get(f"/v1/projects/{project}/failures?kind=sample", headers=key).json()["data"]
    assert [sample["sample_id"] for sample in failures] == ["1", "3"]
    assert all(sample["decision"] is None and sample["category"] == "observed_error" for sample in failures)
    post(f"/projects/{project}/experiments", {"name": "Unsupported classification comparison", "dataset_id": dataset["id"], "snapshot_id": snap["id"], "environment": "dev", "variants": [{"name": "v1", "model_version_id": model["id"]}]}, key, expected=422)
