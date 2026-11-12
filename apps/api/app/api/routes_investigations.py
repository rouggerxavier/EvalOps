"""F2 investigation and evidence endpoints reuse task authorization and receipts."""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app import models as m
from app.api.routes_tasks import task_db, visible_list
from app.domain.tasks import service as s
from app.domain.tasks.investigations import InvestigationCreate, InvestigationPatch, revise
from app.domain.tasks.contracts import LabelDeclaration, Environment

router = APIRouter(prefix="/v1")


@router.post("/projects/{project_id}/investigations", status_code=201)
def create_investigation(project_id: str, payload: InvestigationCreate, request: Request, db: Session = Depends(task_db)):
    actor = s.authenticate(request, db, "write")
    s.project_access(db, actor, project_id, "write")
    row = s.write(db, actor, request, project_id, payload.model_dump(mode="json"),
                  lambda: revise(db, actor, project_id, payload.state, payload.environment))
    return s.serialize(row)


@router.get("/projects/{project_id}/investigations")
def list_investigations(project_id: str, request: Request, limit: int = Query(100, ge=1, le=500),
                        cursor: int = Query(0, ge=0), db: Session = Depends(task_db)):
    actor = s.authenticate(request, db)
    s.project_access(db, actor, project_id)
    return visible_list(db, actor, "investigation", db.query(m.Investigation).filter_by(project_id=project_id), limit, cursor)


@router.get("/investigations/{investigation_id}")
def get_investigation(investigation_id: str, request: Request, db: Session = Depends(task_db)):
    return s.serialize(s.load(db, s.authenticate(request, db), "investigation", investigation_id))


@router.patch("/investigations/{investigation_id}")
def patch_investigation(investigation_id: str, payload: InvestigationPatch, request: Request, db: Session = Depends(task_db)):
    actor = s.authenticate(request, db, "write")
    current = s.load(db, actor, "investigation", investigation_id, permission="write")
    raw = request.headers.get("if-match", "")
    if not raw.isascii() or not raw.isdecimal() or len(raw) > 10:
        raise HTTPException(409, "investigation_revision_conflict")
    row = s.write(db, actor, request, current.project_id, payload.model_dump(mode="json"),
                  lambda: revise(db, actor, current.project_id, payload.state, current.environment, investigation_id, int(raw)))
    return s.serialize(row)


@router.get("/investigations/{investigation_id}/revisions")
def history(investigation_id: str, request: Request, limit: int = Query(100, ge=1, le=500),
            cursor: int = Query(0, ge=0), db: Session = Depends(task_db)):
    actor = s.authenticate(request, db)
    s.load(db, actor, "investigation", investigation_id)
    rows = db.query(m.InvestigationRevision).filter_by(investigation_id=investigation_id).order_by(m.InvestigationRevision.revision).offset(cursor).limit(limit+1).all()
    for row in rows[:limit]:
        s.load(db, actor, "investigation_revision", row.id)
    return {"data": [s.serialize(row) for row in rows[:limit]], "next_cursor": cursor+limit if len(rows)>limit else None}


@router.get("/datasets/{dataset_id}")
def dataset_detail(dataset_id: str, request: Request, db: Session = Depends(task_db)):
    return s.serialize(s.load(db, s.authenticate(request, db), "dataset", dataset_id))


@router.get("/datasets/{dataset_id}/cases")
def cases(dataset_id: str, request: Request, limit: int = Query(100, ge=1, le=500),
          cursor: int = Query(0, ge=0), db: Session = Depends(task_db)):
    actor = s.authenticate(request, db)
    s.load(db, actor, "dataset", dataset_id)
    return visible_list(db, actor, "item", db.query(m.DatasetItem).filter_by(dataset_id=dataset_id), limit, cursor)


@router.post("/task-resources/dataset/{dataset_id}/classify")
def classify_dataset(dataset_id: str, payload: LabelDeclaration, request: Request, db: Session = Depends(task_db)):
    actor = s.authenticate(request, db)
    dataset = s.load(db, actor, "dataset", dataset_id, permission="admin")
    def operation():
        # The shared write lock is already held; refresh before testing initial classification.
        db.refresh(dataset)
        if dataset.access_label is not None:
            raise HTTPException(409, "origin_already_classified")
        project = s.project_access(db, actor, dataset.project_id, "admin")
        label = s.declare_label(db, actor, project, payload)
        dataset.access_label = label
        db.flush()
        for item in db.query(m.DatasetItem).filter_by(dataset_id=dataset_id):
            if item.access_label is not None:
                raise HTTPException(409, "item_already_classified")
            refs = item.metadata_json.get("evalops_case", {}).get("source_refs", [])
            if not refs and item.metadata_json.get("source_trace_id"):
                refs = [f"trace:{item.metadata_json['source_trace_id']}"]
            item.access_label = s.derived_label(db, [f"dataset:{dataset_id}", *refs], dataset.project_id, payload.environment)
        return "dataset", dataset
    return s.serialize(s.write(db, actor, request, dataset.project_id, payload.model_dump(mode="json"), operation))


@router.get("/task-evidence/traces/{trace_id}")
def trace_evidence(trace_id: str, request: Request, db: Session = Depends(task_db)):
    actor = s.authenticate(request, db)
    row = s.load(db, actor, "trace", trace_id)
    if row.deleted_at is not None:
        raise HTTPException(404, "not_found")
    from app.api.routes import get_trace
    from app.domain.rubrics.resolver import build_trace_context
    spans = db.query(m.Span).filter_by(trace_id=trace_id).order_by(m.Span.started_at).all()
    return {**get_trace(row, db), "reference_status": "draft", "source_ref": f"trace:{row.id}",
            "observed_output": build_trace_context(row, spans)["trace"]["output"]["text"]}



@router.get("/projects/{project_id}/failures")
def failures(project_id: str, request: Request, kind: str = Query("trace", pattern="^(trace|sample)$"),
             limit: int = Query(100, ge=1, le=500), cursor: int = Query(0, ge=0), environment: Environment | None = None, db: Session = Depends(task_db)):
    actor = s.authenticate(request, db)
    s.project_access(db, actor, project_id)
    if kind == "sample":
        query = db.query(m.TaskEvaluation).filter_by(project_id=project_id).order_by(m.TaskEvaluation.id)
        if environment:
            query = query.filter(m.TaskEvaluation.environment == environment)
        data = []
        for evaluation in query:
            try:
                s.load(db, actor, "evaluation", evaluation.id)
            except HTTPException as exc:
                if exc.status_code == 404: continue
                raise
            fact = db.query(m.MetricFact).filter_by(task_evaluation_id=evaluation.id, definition_id="regression.residuals", scope="dataset").one_or_none()
            classification = evaluation.result["evaluator_manifest"].get("id") == "classification.standard"
            if classification:
                fact = db.query(m.MetricFact).filter_by(task_evaluation_id=evaluation.id, definition_id="classification.correctness", scope="dataset").one_or_none()
            common = {"kind": "sample", "evaluation_id": evaluation.id, "environment": evaluation.environment,
                      "decision": None, "unit": fact.content["unit"] if fact else None,
                      "evidence_url": f"/v1/task-evaluations/{evaluation.id}/samples"}
            points = (fact.content.get("value") or {}).get("points", []) if fact else []
            if not points:
                data.append({**common, "sample_id": None, "state": fact.content["state"] if fact else "error",
                             "reason": fact.content["reason"] if fact else "missing_metrics", "residual": None,
                             "category": "technical" if not fact or fact.content["state"] == "error" else "missing_evidence"})
            for point in points:
                if point["state"] == "measured" and point["y"] == (1 if classification else 0): continue
                data.append({**common, "sample_id": point["key"], "state": point["state"], "reason": point["reason"],
                             **({"correctness": point["y"]} if classification else {"residual": point["y"]}), "category": "observed_error" if point["state"] == "measured" else "missing_evidence"})
                if len(data)>cursor+limit: break
            if len(data)>cursor+limit: break
        return {"data": data[cursor:cursor+limit], "next_cursor": cursor+limit if len(data)>cursor+limit else None}
    failed_evaluation = db.query(m.EvaluationRun.id).filter(m.EvaluationRun.trace_id==m.Trace.id, m.EvaluationRun.passed.is_(False)).exists()
    query = db.query(m.Trace).filter(m.Trace.project_id==project_id, m.Trace.deleted_at.is_(None), or_(m.Trace.status=="error", failed_evaluation))
    if actor.environment:
        query = query.filter(m.Trace.environment==actor.environment)
    if environment:
        query = query.filter(m.Trace.environment==environment)
    rows = query.order_by(m.Trace.id).offset(cursor).limit(limit+1).all()
    return {"data": [{"kind": "trace", "id": row.id, "name": row.name, "environment": row.environment,
        "execution_status": row.status, "category": "technical" if row.status=="error" else "legacy_quality_signal",
        "decision": None, "reference_status": "draft", "source_ref": f"trace:{row.id}",
        "evidence_url": f"/v1/task-evidence/traces/{row.id}"} for row in rows[:limit]],
        "next_cursor": cursor+limit if len(rows)>limit else None}
