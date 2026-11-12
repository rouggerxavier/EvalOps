"""Owner policy/registry and narrowly scoped runner credentials."""
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import AwareDatetime
from sqlalchemy.orm import Session

from app import models as m
from app.api.routes_tasks import task_db
from app.domain.tasks import service as s
from app.domain.tasks.contracts import Contract
from app.domain.tasks.runner_control import ExecutionPolicy, RunnerRegistration, authenticate_runner, policy_revision, register_runner
from app.security import generate_api_key, hash_api_key, new_id
from app.timestamps import server_timestamp

router = APIRouter(prefix="/v1")


def admin(request, db, project_id):
    actor = s.authenticate(request, db)
    s.project_access(db, actor, project_id, "admin")
    return actor


@router.get("/projects/{project_id}/execution-policy")
def get_policy(project_id: str, request: Request, db: Session = Depends(task_db)):
    admin(request, db, project_id)
    row = db.query(m.ExecutionPolicyRevision).filter_by(project_id=project_id).order_by(m.ExecutionPolicyRevision.version.desc()).first()
    return s.serialize(row) if row else {"project_id": project_id, "version": 0, "policy": ExecutionPolicy().model_dump(mode="json"), "content_hash": None}


@router.put("/projects/{project_id}/execution-policy")
def put_policy(project_id: str, payload: ExecutionPolicy, request: Request, db: Session = Depends(task_db)):
    actor = admin(request, db, project_id)
    raw = request.headers.get("if-match", "")
    if not raw.isascii() or not raw.isdecimal() or len(raw) > 10:
        raise HTTPException(409, "execution_policy_revision_conflict")
    receipt = payload.model_dump(mode="json", exclude={"max_wall_time_s", "max_tool_calls", "max_tokens"} - payload.model_fields_set)
    return s.serialize(s.write(db, actor, request, project_id, receipt,
                               lambda: policy_revision(db, actor, project_id, payload, int(raw))))


@router.post("/projects/{project_id}/runners", status_code=201)
def create_runner(project_id: str, payload: RunnerRegistration, request: Request, db: Session = Depends(task_db)):
    actor = admin(request, db, project_id)
    receipt = payload.model_dump(mode="json", exclude={"max_parallel"} - payload.model_fields_set)
    return s.serialize(s.write(db, actor, request, project_id, receipt,
                               lambda: register_runner(db, actor, project_id, payload)))


@router.get("/projects/{project_id}/runners")
def list_runners(project_id: str, request: Request, limit: int = Query(100, ge=1, le=500), cursor: int = Query(0, ge=0, le=2147483647), db: Session = Depends(task_db)):
    admin(request, db, project_id)
    rows = db.query(m.Runner).filter_by(project_id=project_id).order_by(m.Runner.id).offset(cursor).limit(limit+1).all()
    return {"data": [s.serialize(row) for row in rows[:limit]], "next_cursor": cursor+limit if len(rows)>limit else None}


@router.get("/runners/{runner_id}")
def get_runner(runner_id: str, request: Request, db: Session = Depends(task_db)):
    return s.serialize(s.load(db, s.authenticate(request, db), "runner", runner_id, permission="admin"))


@router.post("/runners/{runner_id}/disable")
def disable_runner(runner_id: str, request: Request, db: Session = Depends(task_db)):
    actor = s.authenticate(request, db)
    runner = s.load(db, actor, "runner", runner_id, permission="admin")
    def disable():
        db.refresh(runner)
        if runner.disabled_at is None:
            runner.disabled_at = m.utcnow()
            s.audit(db, actor, runner.project_id, "runner.disabled", f"runner:{runner.id}")
        return "runner", runner
    return s.serialize(s.write(db, actor, request, runner.project_id, {}, disable))


class CredentialCreate(Contract):
    expires_at: AwareDatetime


@router.post("/runners/{runner_id}/credentials", status_code=201)
def create_credential(runner_id: str, payload: CredentialCreate, request: Request, response: Response, db: Session = Depends(task_db)):
    actor = s.authenticate(request, db)
    runner = s.load(db, actor, "runner", runner_id, permission="admin")
    # Hold the same project write lock as disable before minting a credential.
    db.query(m.Project).filter_by(id=runner.project_id).update({m.Project.name: m.Project.name}, synchronize_session=False)
    db.refresh(runner)
    s.project_access(db, actor, runner.project_id, "admin")
    if runner.disabled_at:
        raise HTTPException(409, "runner_disabled")
    project = db.get(m.Project, runner.project_id)
    responsible = db.get(m.Membership, (runner.owner_user_id, project.organization_id))
    if responsible is None or responsible.role != "owner":
        raise HTTPException(409, "runner_owner_inactive")
    if not m.utcnow() < payload.expires_at <= m.utcnow() + timedelta(days=90):
        raise HTTPException(422, "runner_credential_expiry_must_be_within_90_days")
    raw, prefix = generate_api_key("runner")
    row = m.RunnerCredential(id=new_id("runnerkey"), project_id=runner.project_id, runner_id=runner.id,
        prefix=prefix, hash=hash_api_key(raw), expires_at=payload.expires_at)
    db.add(row); db.flush()
    s.audit(db, actor, runner.project_id, "runner.credential.created", f"runner:{runner.id}")
    response.headers["Cache-Control"] = "no-store"
    return {"id": row.id, "runner_id": runner.id, "key": raw, "prefix": prefix,
            "expires_at": server_timestamp(row.expires_at).isoformat(), "credential_kind": "runner_only", "dispatch_available": False}


@router.post("/runners/{runner_id}/credentials/{credential_id}/revoke")
def revoke_credential(runner_id: str, credential_id: str, request: Request, db: Session = Depends(task_db)):
    actor = s.authenticate(request, db)
    credential = db.get(m.RunnerCredential, credential_id)
    if credential is None or credential.runner_id != runner_id:
        raise HTTPException(404, "not_found")
    s.project_access(db, actor, credential.project_id, "admin")
    if credential.revoked_at is None:
        credential.revoked_at = m.utcnow()
        s.audit(db, actor, credential.project_id, "runner.credential.revoked", f"runner:{credential.runner_id}")
    return {"id": credential.id, "revoked_at": server_timestamp(credential.revoked_at).isoformat()}


@router.get("/runners/{runner_id}/capabilities")
def runner_capabilities(runner_id: str, request: Request, db: Session = Depends(task_db)):
    runner, _ = authenticate_runner(db, runner_id, request.headers.get("x-evalops-runner-key"))
    return {"runner_id": runner.id, "project_id": runner.project_id, "capabilities": runner.capabilities,
            "dispatch_available": False, "managed_sandbox": False}
