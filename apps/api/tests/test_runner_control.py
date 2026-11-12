"""Runner credentials remain isolated from normal API identities; policies are revisioned."""
from datetime import timedelta

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


def runner_body():
    return {"name": "Local fixture", "environments": ["dev"], "adapter_versions": [{"id": "fixture", "version": "1"}]}


def create_runner(headers, project):
    return h.post(f"/projects/{project}/runners", runner_body(), headers)


def credential(headers, runner):
    response = h.client.post(f"/v1/runners/{runner['id']}/credentials", json={"expires_at": (m.utcnow()+timedelta(hours=1)).isoformat()}, headers=headers)
    assert response.status_code == 201, response.text
    assert response.headers["cache-control"] == "no-store"
    return response.json()


def test_policy_compare_and_swap_and_immutable_history():
    headers, project, _ = h.bootstrap()
    url = f"/v1/projects/{project}/execution-policy"
    assert h.client.get(url, headers=headers).json()["version"] == 0
    body = {"enabled": True, "allowed_adapters": [{"id": "fixture", "version": "1"}], "max_cost_per_run_usd": "0.01", "monthly_budget_usd": "1.00"}
    first = h.client.put(url, headers={**headers, "If-Match": "0", "Idempotency-Key": "policy"}, json=body)
    assert first.status_code == 200, first.text
    assert first.json()["version"] == 1
    assert h.client.put(url, headers={**headers, "If-Match": "0", "Idempotency-Key": "policy"}, json=body).json() == first.json()
    assert h.client.put(url, headers={**headers, "If-Match": "0", "Idempotency-Key": "other"}, json=body).status_code == 409
    with SessionLocal() as db:
        with pytest.raises(DBAPIError, match="immutable_task_resource"):
            db.execute(text("UPDATE execution_policy_revisions SET content='{}'")); db.commit()


def test_runner_credential_cannot_read_api_and_revocation_is_immediate():
    headers, project, _ = h.bootstrap()
    runner = create_runner(headers, project)
    key = credential(headers, runner)
    scoped = {"X-EvalOps-Runner-Key": key["key"]}
    url = f"/v1/runners/{runner['id']}/capabilities"
    capabilities = h.client.get(url, headers=scoped)
    assert capabilities.status_code == 200 and capabilities.json()["dispatch_available"] is False
    assert h.client.get(f"/v1/projects/{project}/capabilities", headers={"X-EvalOps-Key": key["key"]}).status_code == 401
    listing = h.client.get(f"/v1/projects/{project}/runners", headers=headers)
    assert key["key"] not in listing.text and '"hash"' not in listing.text
    h.post(f"/runners/{runner['id']}/credentials/{key['id']}/revoke", {}, headers, expected=200)
    assert h.client.get(url, headers=scoped).status_code == 401


@pytest.mark.parametrize("loss", ["disabled", "expired", "owner_removed", "wrong_runner"])
def test_runner_identity_revalidates_current_state(loss):
    headers, project, org = h.bootstrap()
    runner = create_runner(headers, project)
    key = credential(headers, runner)
    scoped = {"X-EvalOps-Runner-Key": key["key"]}
    if loss == "disabled": h.post(f"/runners/{runner['id']}/disable", {}, headers, expected=200)
    if loss == "wrong_runner": runner = create_runner(headers, project)
    with SessionLocal() as db:
        if loss == "expired": db.get(m.RunnerCredential, key["id"]).expires_at = m.utcnow()-timedelta(seconds=1)
        if loss == "owner_removed": db.get(m.Membership, ("user", org)).role = "member"
        db.commit()
    assert h.client.get(f"/v1/runners/{runner['id']}/capabilities", headers=scoped).status_code == 401


def test_other_owner_cannot_mint_for_runner_with_inactive_responsible_owner():
    from app.security import create_access_token
    headers, project, org = h.bootstrap()
    runner = create_runner(headers, project)
    with SessionLocal() as db:
        db.add(m.User(id="second", email="second@example.test", name="Second owner"))
        db.add(m.Membership(user_id="second", organization_id=org, role="owner"))
        db.get(m.Membership, ("user", org)).role = "member"
        db.commit()
    second = {"Authorization": "Bearer " + create_access_token(sub="second", email="second@example.test", name="Second owner")}
    response = h.client.post(f"/v1/runners/{runner['id']}/credentials", headers=second, json={"expires_at": (m.utcnow()+timedelta(hours=1)).isoformat()})
    assert response.status_code == 409 and response.json()["detail"] == "runner_owner_inactive"
    with SessionLocal() as db:
        assert db.query(m.RunnerCredential).count() == 0


def test_registry_pagination_and_detail_preserve_scope_and_never_return_secret():
    headers, project, org = h.bootstrap()
    first = create_runner(headers, project)
    second = create_runner(headers, project)
    key = credential(headers, first)
    page = h.client.get(f"/v1/projects/{project}/runners?limit=1", headers=headers).json()
    following = h.client.get(f"/v1/projects/{project}/runners?limit=1&cursor={page['next_cursor']}", headers=headers).json()
    assert {page["data"][0]["id"], following["data"][0]["id"]} == {first["id"], second["id"]}
    assert following["next_cursor"] is None
    detail = h.client.get(f"/v1/runners/{first['id']}", headers=headers)
    assert detail.json() == first and key["key"] not in detail.text and '"hash"' not in detail.text
    with SessionLocal() as db:
        with pytest.raises(DBAPIError, match="immutable_task_resource"):
            db.execute(text("UPDATE runners SET capabilities='{}'")); db.commit()


def test_old_policy_and_registration_receipts_survive_new_default_limits():
    from app.domain.tasks.contracts import digest
    headers, project, _ = h.bootstrap()
    policy_path = f"/v1/projects/{project}/execution-policy"
    policy_headers = {**headers, "If-Match": "0", "Idempotency-Key": "legacy-policy"}
    first = h.client.put(policy_path, headers=policy_headers, json={})
    assert first.status_code == 200
    runner = h.post(f"/projects/{project}/runners", runner_body(), headers, key="legacy-runner")
    with SessionLocal() as db:
        policy_receipt = db.query(m.TaskReceipt).filter_by(key="legacy-policy").one()
        policy_receipt.body_hash = digest({"enabled": False, "environments": ["dev"], "allowed_adapters": [],
            "max_cost_per_run_usd": "0", "monthly_budget_usd": "0", "max_parallel": 1, "effects_policy": "fixtures_only"})
        runner_receipt = db.query(m.TaskReceipt).filter_by(key="legacy-runner").one()
        runner_receipt.body_hash = digest({**runner_body(), "isolation": "client_managed"})
        db.commit()
    assert h.client.put(policy_path, headers=policy_headers, json={}).json() == first.json()
    assert h.post(f"/projects/{project}/runners", runner_body(), headers, key="legacy-runner") == runner
