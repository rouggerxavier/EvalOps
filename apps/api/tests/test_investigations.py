"""F2 continuity, provenance, mutable cases and source restrictions through real HTTP/DB."""
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


def create(headers, project, refs=(), **state):
    return h.post(f"/projects/{project}/investigations", {"environment": "dev", "state": {"title": "Investigate", "evidence_refs": list(refs), **state}}, headers)


def test_revision_continuity_receipt_and_stale_write():
    headers, project, _ = h.bootstrap()
    key, principal, _ = h.key_for(headers, project)
    first = create(key, project, next_steps=["Review the cases"])
    assert first["revision"] == 1 and first["author_kind"] == "service" and first["author_id"] == principal["id"]
    path = f"/v1/investigations/{first['id']}"
    assert h.client.get(path, headers=headers).json() == first
    body = {"state": {"title": "Reviewed", "status": "resolved", "summary": "Checked evidence"}}
    patch_headers = {**headers, "If-Match": "1", "Idempotency-Key": "patch"}
    response = h.client.patch(path, headers=patch_headers, json=body)
    assert response.status_code == 200, response.text
    second = response.json()
    assert second["revision"] == 2 and second["author_kind"] == "human"
    assert h.client.patch(path, headers=patch_headers, json=body).json() == second
    stale = h.client.patch(path, headers={**patch_headers, "Idempotency-Key": "new"}, json=body)
    assert stale.status_code == 409
    history = h.client.get(path+"/revisions", headers=key).json()["data"]
    assert [row["revision"] for row in history] == [1,2]
    assert history[0]["title"] == "Investigate" and history[1]["title"] == "Reviewed"
    with SessionLocal() as db:
        with pytest.raises(DBAPIError, match="immutable_task_resource"):
            db.execute(text("UPDATE investigation_revisions SET state='{}' WHERE investigation_id=:id"), {"id": first["id"]})
            db.commit()


def test_removing_reference_does_not_remove_source_restrictions():
    headers, project, _ = h.bootstrap()
    dataset, snap, _, predictions = h.fixture(headers, project)
    result = h.post(f"/projects/{project}/task-evaluations", {"prediction_set_id": predictions["id"]}, headers)
    first = create(headers, project, refs=[f"evaluation:{result['id']}"])
    path = f"/v1/investigations/{first['id']}"
    response = h.client.patch(path, headers={**headers, "If-Match": "1", "Idempotency-Key": "clear"}, json={"state": {"title": "Reference removed"}})
    assert response.status_code == 200
    key, _, _ = h.key_for(headers, project)
    assert h.client.get(path, headers=key).status_code == 200
    with SessionLocal() as db:
        dataset_row = db.get(m.Dataset, dataset["id"])
        dataset_row.access_label = {**dataset_row.access_label, "allowed_environments": ["prod"]}
        db.commit()
    for url in (path, path+"/revisions"):
        assert h.client.get(url, headers=key).status_code == 404
        assert h.client.get(url, headers=headers).status_code == 404
    assert h.client.get(f"/v1/projects/{project}/investigations", headers=key).json()["data"] == []


def test_text_case_requires_owner_classification_and_human_review():
    headers, project, org = h.bootstrap()
    dataset = h.post(f"/projects/{project}/datasets", {"slug": "observed"}, headers)
    key, _, _ = h.key_for(headers, project)
    assert h.client.get(f"/v1/datasets/{dataset['id']}", headers=key).status_code == 404
    h.post(f"/task-resources/dataset/{dataset['id']}/classify", {"environment": "dev"}, headers, expected=200)
    with SessionLocal() as db:
        db.add(m.Trace(id="trace", project_id=project, organization_id=org, environment="dev", name="Failure", status="error", started_at=m.utcnow(), ended_at=m.utcnow(), duration_ms=0))
        db.commit()
    failures = h.client.get(f"/v1/projects/{project}/failures", headers=key).json()["data"]
    assert failures[0]["category"] == "technical" and failures[0]["decision"] is None
    evidence = h.client.get("/v1/task-evidence/traces/trace", headers=key)
    assert evidence.status_code == 200 and evidence.json()["reference_status"] == "draft"
    case = h.post(f"/datasets/{dataset['id']}/cases", {"environment": "dev", "source_refs": ["trace:trace"],
        "case": {"sample_id": "observed", "input": {"messages": []}, "expected_output": {"assistant_message": "proposed"}}}, key)
    assert case["reference_status"] == "draft"
    patch = {"case": {"sample_id": "observed", "input": {}, "expected_output": {"assistant_message": "human corrected"}, "reference_status": "reviewed"}, "review_reason": "Checked manually"}
    url = f"/v1/datasets/{dataset['id']}/cases/{case['id']}"
    assert h.client.patch(url, headers={**key, "If-Match": "1", "Idempotency-Key": "case-patch"}, json=patch).status_code == 403
    assert h.client.patch(url, headers={**headers, "If-Match": "1", "Idempotency-Key": "case-patch"}, json=patch).status_code == 200
    inv = create(key, project, refs=[f"item:{case['id']}"])
    with SessionLocal() as db:
        db.get(m.Trace, "trace").deleted_at = m.utcnow(); db.commit()
    assert h.client.get(f"/v1/investigations/{inv['id']}", headers=key).status_code == 404


def test_cross_project_reference_and_prospective_cycle():
    headers, project, org = h.bootstrap()
    first = create(headers, project)
    dataset, _, _, _ = h.fixture(headers, project)
    case = h.post(f"/datasets/{dataset['id']}/cases", {"environment": "dev", "source_refs": [f"investigation:{first['id']}"], "case": {"sample_id": "cycle", "input": {}}}, headers)
    response = h.client.patch(f"/v1/investigations/{first['id']}", headers={**headers, "If-Match": "1", "Idempotency-Key": "cycle"}, json={"state": {"title": "Cycle", "evidence_refs": [f"item:{case['id']}"]}})
    assert response.status_code == 422 and response.json()["detail"] == "cyclic_evidence"
    other = h.post("/projects", {"organization_id": org, "name": "Other", "slug": "other"}, headers)
    h.post(f"/projects/{other['id']}/investigations", {"environment": "dev", "state": {"title": "Wrong project", "evidence_refs": [f"item:{case['id']}"]}}, headers, expected=404)
