"""Sealed plans and budget admission; no code executes in the API process."""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app import models as m
from app.api.routes_tasks import task_db, visible_list
from app.domain.tasks import execution_budget as budget
from app.domain.tasks import execution_plans as plans
from app.domain.tasks import service as s

router = APIRouter(prefix="/v1")


@router.get("/projects/{project_id}/organization-execution-budget")
def get_organization_budget(project_id: str, request: Request, db: Session = Depends(task_db)):
    project = s.project_access(db, s.authenticate(request, db), project_id, "admin")
    return budget.serialize_budget(budget.current_budget(db, project.organization_id), project.organization_id)


@router.put("/projects/{project_id}/organization-execution-budget")
def put_organization_budget(project_id: str, payload: budget.OrganizationBudget, request: Request, db: Session = Depends(task_db)):
    actor = s.authenticate(request, db)
    s.project_access(db, actor, project_id, "admin")
    raw = request.headers.get("if-match", "")
    if not raw.isascii() or not raw.isdecimal() or len(raw) > 10:
        raise HTTPException(409, "organization_budget_revision_conflict")
    return budget.update_budget(db, actor, project_id, payload, int(raw))


@router.post("/projects/{project_id}/execution-plans", status_code=201)
def create_plan(project_id: str, payload: plans.PlanCreate, request: Request, db: Session = Depends(task_db)):
    actor = s.authenticate(request, db, "write")
    s.project_access(db, actor, project_id, "write")
    return s.serialize(s.write(db, actor, request, project_id, payload.model_dump(mode="json"),
                               lambda: plans.create_plan(db, actor, project_id, payload)))


@router.get("/projects/{project_id}/execution-plans")
def list_plans(project_id: str, request: Request, limit: int = Query(100, ge=1, le=500), cursor: int = Query(0, ge=0), db: Session = Depends(task_db)):
    actor = s.authenticate(request, db)
    s.project_access(db, actor, project_id)
    return visible_list(db, actor, "plan", db.query(m.ExecutionPlan).filter_by(project_id=project_id), limit, cursor)


@router.get("/execution-plans/{plan_id}")
def get_plan(plan_id: str, request: Request, db: Session = Depends(task_db)):
    return s.serialize(s.load(db, s.authenticate(request, db), "plan", plan_id))


@router.post("/projects/{project_id}/executions", status_code=202)
def create_execution(project_id: str, payload: plans.ExecutionCreate, request: Request, db: Session = Depends(task_db)):
    actor = s.authenticate(request, db, "evaluate")
    s.project_access(db, actor, project_id, "evaluate")
    s.project_access(db, actor, project_id, "write")
    return s.serialize(s.write(db, actor, request, project_id, payload.model_dump(mode="json"),
                               lambda: plans.create_execution(db, actor, request, project_id, payload)))


@router.post("/executions/{execution_id}/cancel")
def cancel_execution(execution_id: str, request: Request, db: Session = Depends(task_db)):
    return plans.cancel_execution(db, s.authenticate(request, db, "evaluate"), execution_id, request)


@router.get("/executions/{execution_id}/budget")
def execution_budget(execution_id: str, request: Request, db: Session = Depends(task_db)):
    s.load(db, s.authenticate(request, db), "execution", execution_id)
    reservation = db.get(m.ExecutionReservation, execution_id)
    if reservation is None:
        raise HTTPException(404, "not_found")
    entries = db.query(m.ExecutionLedgerEntry).filter_by(execution_id=execution_id).order_by(m.ExecutionLedgerEntry.created_at, m.ExecutionLedgerEntry.id).all()
    return {"execution_id": execution_id, "currency": "USD", "state": reservation.state, "slots_active": reservation.active,
            "reserved_limit_usd": format(budget.usd(reservation.reserved_units), "f"),
            "known_spent_usd": format(budget.usd(reservation.spent_units), "f") if reservation.spent_units is not None else None,
            "held_usd": format(budget.usd(reservation.reserved_units if reservation.state != "settled" else 0), "f"),
            "entries": [{"id": row.id, "kind": row.kind, "amount_usd": format(budget.usd(row.amount_units), "f"), "measurement_source": row.measurement_source,
                         "pricing_version": row.pricing_version} for row in entries]}
