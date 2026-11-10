"""External harness capture is immutable, source-bound and explicitly unverified."""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app import models as m
from app.db import Base, SessionLocal, engine
import test_offline_task_api as h


@pytest.fixture(autouse=True)
def isolated():
    Base.metadata.drop_all(engine); Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


def payload(snapshot, model, predictions=None):
    hashed = "sha256:" + "0" * 64
    return {"manifest": {"mode": "application_adapter", "environment": "dev", "snapshot_id": snapshot["id"], "snapshot_hash": snapshot["content_hash"],
        "candidate": {"application_ref": "fixture@v1", "code_commit": "fixture-v1", "code_dirty": False, "config_digest": hashed, "model_versions": [model["id"]]},
        "adapter": {"id": "fixture", "version": "1", "environment_digest": hashed, "runtime": "Python fixture"},
        "initial_state_digest": hashed, "fixture_digests": [hashed], "limits": {"max_cost_usd": "1.00", "wall_time_s": 60, "max_tool_calls": 2, "max_tokens": 1000, "max_parallel": 1}},
        "result": {"status": "succeeded" if predictions else "uncertain", "exit_reason": "Fixture capture", "started_at": "2026-11-10T12:00:00Z", "ended_at": "2026-11-10T12:00:01Z",
        "prediction_set_id": predictions["id"] if predictions else None, "capture_status": "complete" if predictions else "uncertain", "cost": {"state": "unknown"}}}


def test_external_capture_roundtrip_idempotency_and_database_guards():
    headers, project, _ = h.bootstrap()
    _, snapshot, model, predictions = h.fixture(headers, project)
    key, _, _ = h.key_for(headers, project)
    body = payload(snapshot, model, predictions)
    path = f"/projects/{project}/execution-imports"
    execution = h.post(path, body, key, key="capture")
    assert h.post(path, body, key, key="capture") == execution
    assert execution["capture_origin"] == "external_import" and execution["decision"] is None
    result = execution["attempts"][0]["result"]
    assert result["cost"]["state"] == "unknown" and result["cost"]["amount_usd"] is None
    assert result["budget_reserved"] is None and result["provenance"] == "partial"
    assert result["input_bindings"]["prediction_hash"] == predictions["content_hash"]
    assert h.client.get(f"/v1/executions/{execution['id']}", headers=headers).json() == execution
    with SessionLocal() as db:
        for table in ("executions", "execution_attempts"):
            with pytest.raises(DBAPIError, match="immutable_task_resource"):
                db.execute(text(f"UPDATE {table} SET id=id")); db.commit()
            db.rollback()
        assert db.query(m.Execution).count() == db.query(m.ExecutionAttempt).count() == 1


def test_binding_restriction_and_explicit_overspend_warning():
    headers, project, _ = h.bootstrap()
    dataset, snapshot, model, predictions = h.fixture(headers, project)
    body = payload(snapshot, model, predictions)
    body["result"]["cost"] = {"state": "provided", "amount_usd": "1.01", "measurement_source": "fixture ledger"}
    key, _, _ = h.key_for(headers, project)
    execution = h.post(f"/projects/{project}/execution-imports", body, key)
    assert "reported_cost_exceeds_declared_limit" in execution["attempts"][0]["result"]["warnings"]
    inv = h.post(f"/projects/{project}/investigations", {"environment": "dev", "state": {"title": "Review execution", "evidence_refs": [f"execution:{execution['id']}"]}}, headers)
    with SessionLocal() as db:
        row = db.get(m.Dataset, dataset["id"])
        row.access_label = {**row.access_label, "allowed_environments": ["prod"]}; db.commit()
    for credentials in (key, headers):
        assert h.client.get(f"/v1/executions/{execution['id']}", headers=credentials).status_code == 404
        assert h.client.get(f"/v1/investigations/{inv['id']}", headers=credentials).status_code == 404
        h.post(f"/projects/{project}/execution-imports", body, credentials, expected=404)


@pytest.mark.parametrize("change", ["hash", "environment", "dirty", "cost", "binding", "effects", "timestamp", "seed", "boolean"])
def test_invalid_capture_never_publishes_partial_rows(change):
    headers, project, _ = h.bootstrap()
    _, snapshot, model, predictions = h.fixture(headers, project)
    body = payload(snapshot, model, predictions)
    if change == "seed": body["manifest"]["seed"] = 10**400
    if change == "boolean": body["manifest"]["candidate"]["code_dirty"] = "false"
    if change == "hash": body["manifest"]["snapshot_hash"] = "sha256:" + "1" * 64
    if change == "environment": body["manifest"]["environment"] = "prod"
    if change == "dirty": body["manifest"]["candidate"]["code_dirty"] = True
    if change == "cost": body["result"]["cost"]["amount_usd"] = "0"
    if change == "binding": body["result"]["prediction_set_id"] = "missing"
    if change == "effects": body["manifest"]["effects_policy"] = "external_write"
    if change == "timestamp": body["result"]["ended_at"] = "2026-11-10T11:00:00Z"
    key, _, _ = h.key_for(headers, project)
    h.post(f"/projects/{project}/execution-imports", body, key, expected=404 if change in {"environment", "binding"} else 422)
    with SessionLocal() as db:
        assert db.query(m.Execution).count() == db.query(m.ExecutionAttempt).count() == 0


def test_shared_snapshot_never_allows_principal_to_publish_another_environment():
    headers, project, _ = h.bootstrap()
    access = {"environment": "dev", "independent": True, "allowed_environments": ["dev", "prod"],
              "justification": "Synthetic independent fixture", "evidence": "Manual fixture v1"}
    dataset = h.post(f"/projects/{project}/datasets", {"slug": "neutral", "task_type": "regression", "task_schema": {"target": {"name": "value", "unit": "1"}}, "access": access, "items": []}, headers)
    snapshot = h.post(f"/datasets/{dataset['id']}/snapshots", {"environment": "dev", "allowed_environments": ["dev", "prod"]}, headers)
    model = h.post(f"/projects/{project}/model-versions", {"model": {"name": "neutral", "version_ref": "1"}, "access": access}, headers)
    key, _, _ = h.key_for(headers, project, env="prod")
    assert h.client.get(f"/v1/dataset-snapshots/{snapshot['id']}", headers=key).status_code == 200
    h.post(f"/datasets/{dataset['id']}/snapshots", {"environment": "dev"}, key, expected=404)
    h.post(f"/projects/{project}/execution-imports", payload(snapshot, model), key, expected=404)
    with SessionLocal() as db:
        assert db.query(m.Execution).count() == 0
