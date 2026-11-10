"""Offline task endpoints. SDK and web consume these persisted results."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app import models as m
from app.db import get_db
from app.domain.tasks import service as s
from app.domain.tasks.contracts import (
    AccessLabel, Environment, ModelCreate, PredictionImport, EvaluationCreate, SnapshotContent, TaskDatasetCreate,
)
from app.security import new_id

router = APIRouter(prefix="/v1")


def task_db(request: Request, db: Session = Depends(get_db)):
    try:
        yield db
        key_id = getattr(request.state, "api_key_id", None)
        if key_id:
            key = db.get(m.ApiKey, key_id)
            if key:
                key.last_used_at = m.utcnow()
        db.commit()
    except Exception:
        db.rollback()
        raise


class SnapshotRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    environment: Environment
    allowed_environments: tuple[Environment, ...] | None = None


class PrincipalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=2, max_length=255)


@router.get("/projects/{project_id}/capabilities")
def capabilities(project_id: str, request: Request, db: Session = Depends(task_db)):
    actor = s.authenticate(request, db)
    project = s.project_access(db, actor, project_id)
    if actor.user_id:
        membership = db.get(m.Membership, (actor.user_id, project.organization_id))
        permissions = ["read", "write", "evaluate"] if membership.role in {"owner", "member"} else ["read"]
        if membership.role == "owner": permissions.append("admin")
    else:
        permissions = sorted(actor.scopes)
    return {"schema_version": 1, "task_types": ["regression", "classification"],
            "evaluator_versions": [{"id": "regression.standard", "version": "1"}, {"id": "classification.standard", "version": "1"}],
            "limits": {"max_rows": 10000, "max_import_bytes": 10 * 1024 * 1024, "max_segments": 8, "max_segment_groups": 1000, "max_group_key_bytes": 2048, "max_classes": 100, "max_class_group_pairs": 2000},
            "permissions": permissions,
            "execution_capabilities": {"import": True, "dispatch": False, "managed_sandbox": False},
            "links": {"executions": f"/v1/projects/{project_id}/executions", "evaluations": f"/v1/projects/{project_id}/task-evaluations",
                      "investigations": f"/v1/projects/{project_id}/investigations", "failures": f"/v1/projects/{project_id}/failures"}}


@router.post("/projects/{project_id}/service-principals", status_code=201)
def create_principal(project_id: str, payload: PrincipalRequest, request: Request, db: Session = Depends(task_db)):
    actor = s.authenticate(request, db)
    s.project_access(db, actor, project_id, "admin")
    if not actor.user_id:
        raise HTTPException(403, "forbidden")
    def operation():
        row = m.ServicePrincipal(id=new_id("principal"), project_id=project_id, name=payload.name, owner_user_id=actor.user_id)
        db.add(row)
        return "principal", row
    return s.serialize(s.write(db, actor, request, project_id, payload.model_dump(), operation))


@router.get("/projects/{project_id}/service-principals")
def list_principals(project_id: str, request: Request, db: Session = Depends(task_db)):
    actor = s.authenticate(request, db)
    s.project_access(db, actor, project_id, "admin")
    return {"data": [s.serialize(row) for row in db.query(m.ServicePrincipal).filter_by(project_id=project_id).all()]}


@router.post("/service-principals/{principal_id}/disable")
def disable_principal(principal_id: str, request: Request, db: Session = Depends(task_db)):
    actor = s.authenticate(request, db)
    row = db.get(m.ServicePrincipal, principal_id)
    if not row:
        raise HTTPException(404, "not_found")
    s.project_access(db, actor, row.project_id, "admin")
    row.disabled_at = row.disabled_at or m.utcnow()
    s.audit(db, actor, row.project_id, "task.principal.disabled", f"principal:{row.id}")
    db.commit()
    return s.serialize(row)


def create_task_dataset(project_id: str, payload: TaskDatasetCreate, request: Request, db: Session = Depends(task_db)):
    actor = s.authenticate(request, db, "write")
    s.project_access(db, actor, project_id, "write")
    return s.serialize(s.write(db, actor, request, project_id, payload.model_dump(mode="json"),
                               lambda: s.create_dataset(db, actor, project_id, payload)))


@router.post("/datasets/{dataset_id}/snapshots", status_code=201)
def create_snapshot(dataset_id: str, payload: SnapshotRequest, request: Request, db: Session = Depends(task_db)):
    actor = s.authenticate(request, db, "write")
    dataset = s.load(db, actor, "dataset", dataset_id, environment=payload.environment, permission="write")
    return s.serialize(s.write(db, actor, request, dataset.project_id, payload.model_dump(),
                               lambda: s.create_snapshot(db, actor, dataset_id, payload.environment, payload.allowed_environments)))


@router.post("/projects/{project_id}/model-versions", status_code=201)
def create_model(project_id: str, payload: ModelCreate, request: Request, db: Session = Depends(task_db)):
    actor = s.authenticate(request, db, "write")
    s.project_access(db, actor, project_id, "write")
    return s.serialize(s.write(db, actor, request, project_id, payload.model_dump(mode="json"),
                               lambda: s.create_model(db, actor, project_id, payload)))


@router.post("/projects/{project_id}/prediction-sets", status_code=201)
def create_predictions(project_id: str, payload: PredictionImport, request: Request, db: Session = Depends(task_db)):
    actor = s.authenticate(request, db, "write")
    s.project_access(db, actor, project_id, "write")
    return s.serialize(s.write(db, actor, request, project_id, payload.model_dump(mode="json"),
                               lambda: s.create_predictions(db, actor, project_id, payload)))


@router.post("/projects/{project_id}/task-evaluations", status_code=201)
def create_evaluation(project_id: str, payload: EvaluationCreate, request: Request, db: Session = Depends(task_db)):
    actor = s.authenticate(request, db, "evaluate")
    s.project_access(db, actor, project_id, "evaluate")
    return s.serialize(s.write(db, actor, request, project_id, payload.model_dump(mode="json"),
                               lambda: s.create_evaluation(db, actor, project_id, payload)))


@router.get("/dataset-snapshots/{snapshot_id}")
def get_snapshot(snapshot_id: str, request: Request, db: Session = Depends(task_db)):
    return s.serialize(s.load(db, s.authenticate(request, db), "snapshot", snapshot_id))


@router.get("/model-versions/{model_id}")
def get_model(model_id: str, request: Request, db: Session = Depends(task_db)):
    return s.serialize(s.load(db, s.authenticate(request, db), "model", model_id))


@router.get("/prediction-sets/{set_id}")
def get_predictions(set_id: str, request: Request, db: Session = Depends(task_db)):
    return s.serialize(s.load(db, s.authenticate(request, db), "predictions", set_id))


@router.get("/task-evaluations/{evaluation_id}")
def get_evaluation(evaluation_id: str, request: Request, db: Session = Depends(task_db)):
    row = s.load(db, s.authenticate(request, db), "evaluation", evaluation_id)
    result = s.serialize(row)
    result["snapshot_id"] = db.get(m.PredictionSet, row.prediction_set_id).snapshot_id
    return result


@router.get("/task-evaluations/{evaluation_id}/metrics")
def metrics(evaluation_id: str, request: Request, db: Session = Depends(task_db)):
    row = s.load(db, s.authenticate(request, db), "evaluation", evaluation_id)
    facts = db.query(m.MetricFact).filter_by(task_evaluation_id=row.id).order_by(m.MetricFact.id).all()
    return {"data": [{**fact.content, "id": fact.id, "task_evaluation_id": row.id} for fact in facts]}


@router.get("/task-evaluations/{evaluation_id}/samples")
def samples(evaluation_id: str, request: Request, limit: int = Query(100, ge=1, le=500),
            cursor: int = Query(0, ge=0), order: Literal["sample_id", "absolute_error_desc"] = "sample_id", db: Session = Depends(task_db)):
    row = s.load(db, s.authenticate(request, db), "evaluation", evaluation_id)
    predictions = db.get(m.PredictionSet, row.prediction_set_id)
    snapshot = db.get(m.DatasetSnapshot, predictions.snapshot_id)
    items = sorted(SnapshotContent.model_validate_json(snapshot.content).items, key=lambda item: item.sample_id)
    imported = {item.sample_id: item.content for item in db.query(m.Prediction).filter_by(set_id=predictions.id).all()}
    residual_fact = db.query(m.MetricFact).filter_by(task_evaluation_id=row.id, definition_id="regression.residuals", scope="dataset").one_or_none()
    residuals = {point["key"]: point for point in (residual_fact.content.get("value") or {}).get("points", [])} if residual_fact else {}
    if order == "absolute_error_desc":
        items.sort(key=lambda item: (residuals.get(item.sample_id, {}).get("y") is None,
                                    -abs(residuals[item.sample_id]["y"]) if residuals.get(item.sample_id, {}).get("y") is not None else 0,
                                    item.sample_id))
    correct_fact = db.query(m.MetricFact).filter_by(task_evaluation_id=row.id, definition_id="classification.correctness", scope="dataset").one_or_none()
    correctness = {point["key"]: point for point in (correct_fact.content.get("value") or {}).get("points", [])} if correct_fact else {}
    data = []
    for item in items[cursor:cursor + limit]:
        prediction = imported.get(item.sample_id)
        data.append({**item.model_dump(mode="json"), "prediction_row": prediction, "residual": residuals.get(item.sample_id), **({"correctness": correctness.get(item.sample_id)} if correct_fact else {})})
    return {"data": data, "next_cursor": cursor + limit if cursor + limit < len(items) else None}


@router.get("/dataset-snapshots/{snapshot_id}/items")
def snapshot_items(snapshot_id: str, request: Request, limit: int = Query(100, ge=1, le=500),
                   cursor: int = Query(0, ge=0), db: Session = Depends(task_db)):
    row = s.load(db, s.authenticate(request, db), "snapshot", snapshot_id)
    items = sorted(SnapshotContent.model_validate_json(row.content).items, key=lambda item: item.sample_id)
    return {"data": [item.model_dump(mode="json") for item in items[cursor:cursor + limit]],
            "next_cursor": cursor + limit if cursor + limit < len(items) else None}


def visible_list(db, actor, kind, query, limit, cursor):
    visible = []
    for row in query.order_by(s.RESOURCE_MODELS[kind].id):
        try:
            s.load(db, actor, kind, row.id)
        except HTTPException as exc:
            if exc.status_code == 404:
                continue
            raise
        visible.append(row)
        if len(visible) > cursor + limit:
            break
    page = visible[cursor:cursor + limit]
    return {"data": [s.serialize(row) for row in page], "next_cursor": cursor + limit if len(visible) > cursor + limit else None}


@router.get("/projects/{project_id}/model-versions")
def list_models(project_id: str, request: Request, limit: int = Query(100, ge=1, le=500),
                cursor: int = Query(0, ge=0), db: Session = Depends(task_db)):
    actor = s.authenticate(request, db)
    s.project_access(db, actor, project_id)
    return visible_list(db, actor, "model", db.query(m.ModelVersion).filter_by(project_id=project_id), limit, cursor)


@router.get("/projects/{project_id}/task-evaluations")
def list_evaluations(project_id: str, request: Request, environment: Environment | None = None,
                     status: Literal["queued", "running", "succeeded", "failed", "cancelled", "timed_out", "uncertain"] | None = None,
                     model_version: str | None = None, snapshot: str | None = None, limit: int = Query(100, ge=1, le=500),
                     cursor: int = Query(0, ge=0), db: Session = Depends(task_db)):
    actor = s.authenticate(request, db)
    s.project_access(db, actor, project_id)
    query = db.query(m.TaskEvaluation).filter_by(project_id=project_id)
    if environment:
        query = query.filter_by(environment=environment)
    if status:
        query = query.filter_by(status=status)
    if model_version or snapshot:
        query = query.join(m.PredictionSet, m.TaskEvaluation.prediction_set_id == m.PredictionSet.id)
        if model_version:
            query = query.filter(m.PredictionSet.model_version_id == model_version)
        if snapshot:
            query = query.filter(m.PredictionSet.snapshot_id == snapshot)
    return visible_list(db, actor, "evaluation", query, limit, cursor)


@router.get("/datasets/{dataset_id}/snapshots")
def list_snapshots(dataset_id: str, request: Request, limit: int = Query(100, ge=1, le=500),
                   cursor: int = Query(0, ge=0), db: Session = Depends(task_db)):
    actor = s.authenticate(request, db)
    s.load(db, actor, "dataset", dataset_id)
    return visible_list(db, actor, "snapshot", db.query(m.DatasetSnapshot).filter_by(dataset_id=dataset_id), limit, cursor)


@router.get("/prediction-sets/{set_id}/rows")
def prediction_rows(set_id: str, request: Request, limit: int = Query(100, ge=1, le=500),
                    cursor: int = Query(0, ge=0), db: Session = Depends(task_db)):
    actor = s.authenticate(request, db)
    s.load(db, actor, "predictions", set_id)
    query = db.query(m.Prediction).filter_by(set_id=set_id).order_by(m.Prediction.sample_id)
    rows = query.offset(cursor).limit(limit + 1).all()
    return {"data": [row.content for row in rows[:limit]], "next_cursor": cursor + limit if len(rows) > limit else None}


class Restriction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    allowed_environments: tuple[Environment, ...]
    access_revision: int = Field(ge=1, strict=True)


@router.post("/task-resources/{kind}/{resource_id}/restrict")
def restrict(kind: str, resource_id: str, payload: Restriction, request: Request, db: Session = Depends(task_db)):
    if kind not in {"dataset", "snapshot", "model"}:
        raise HTTPException(404, "not_found")
    actor = s.authenticate(request, db)
    row = s.load(db, actor, kind, resource_id, permission="admin")
    db.query(m.Project).filter_by(id=row.project_id).update({m.Project.name: m.Project.name}, synchronize_session=False)
    db.refresh(row)
    current = AccessLabel.model_validate(row.access_label)
    if not payload.allowed_environments or not set(payload.allowed_environments) <= set(current.allowed_environments):
        raise HTTPException(422, "access_may_only_be_restricted")
    updated = {**row.access_label, "allowed_environments": list(payload.allowed_environments),
               "access_revision": current.access_revision + 1}
    if payload.access_revision != current.access_revision:
        raise HTTPException(409, "access_revision_conflict")
    row.access_label = updated
    s.audit(db, actor, row.project_id, "task.access.restricted", f"{kind}:{row.id}")
    db.commit()
    db.refresh(row)
    return s.serialize(row)


# The canonical dataset route preserves textual payloads through the existing handler.
from app.schemas import DatasetCreate
from app.deps import get_current_user


@router.post("/projects/{project_id}/datasets", status_code=201)
def create_dataset(project_id: str, payload: TaskDatasetCreate | DatasetCreate, request: Request,
                   db: Session = Depends(task_db)):
    if isinstance(payload, TaskDatasetCreate):
        return create_task_dataset(project_id, payload, request, db)
    from app.api.routes_phase5 import create_dataset as create_text_dataset
    user = get_current_user(request, request.headers.get("authorization"), db)
    return create_text_dataset(project_id, payload, user, db)


from app.domain.tasks import comparison as c
from app.domain.tasks.contracts import TaskExperimentCreate, ComparisonCreate
from app.schemas import ExperimentCreate


@router.post("/projects/{project_id}/experiments", status_code=201)
def create_experiment(project_id: str, payload: TaskExperimentCreate | ExperimentCreate, request: Request,
                      db: Session = Depends(task_db)):
    if not isinstance(payload, TaskExperimentCreate):
        from app.api.routes_phase5 import create_experiment as legacy
        return legacy(project_id, payload, get_current_user(request, request.headers.get("authorization"), db), db)
    actor = s.authenticate(request, db, "write")
    s.project_access(db, actor, project_id, "write")
    return s.serialize(s.write(db, actor, request, project_id, payload.model_dump(mode="json"),
                               lambda: c.create_experiment(db, actor, project_id, payload)))


@router.post("/experiments/{experiment_id}/comparisons", status_code=201)
def create_comparison(experiment_id: str, payload: ComparisonCreate, request: Request, db: Session = Depends(task_db)):
    actor = s.authenticate(request, db, "evaluate")
    experiment = c.experiment(db, actor, experiment_id, "evaluate")
    run = s.write(db, actor, request, experiment.project_id, payload.model_dump(mode="json"),
                  lambda: c.create_comparison(db, actor, experiment, payload))
    return {"run": s.serialize(run)}


@router.get("/projects/{project_id}/experiments")
def list_experiments(project_id: str, request: Request, view: str | None = None,
                     limit: int = Query(100, ge=1, le=500), cursor: int = Query(0, ge=0), db: Session = Depends(task_db)):
    if view != "task_v1":
        from app.api.routes_phase5 import list_experiments as legacy
        return legacy(project_id, get_current_user(request, request.headers.get("authorization"), db), db)
    actor = s.authenticate(request, db)
    s.project_access(db, actor, project_id)
    return visible_list(db, actor, "experiment", db.query(m.Experiment).filter_by(project_id=project_id, kind="task_comparison"), limit, cursor)


@router.get("/experiments/{experiment_id}/runs")
def list_runs(experiment_id: str, request: Request, view: str | None = None,
              limit: int = Query(20, ge=1, le=100), cursor: int = Query(0, ge=0), db: Session = Depends(task_db)):
    if view != "task_v1" and request.headers.get("x-evalops-key"):
        actor = default_task_actor(request, db)
        experiment = c.experiment(db, actor, experiment_id)
        raise HTTPException(409, "task_view_required")
    if view != "task_v1":
        from app.api.routes_phase5 import list_experiment_runs as legacy
        return legacy(experiment_id, limit, get_current_user(request, request.headers.get("authorization"), db), db)
    actor = s.authenticate(request, db)
    experiment = c.experiment(db, actor, experiment_id)
    query = db.query(m.ExperimentRun).filter_by(experiment_id=experiment_id, kind="task_comparison")
    return visible_list(db, actor, "comparison", query, limit, cursor)


@router.get("/experiments/{experiment_id}/runs/{run_id}")
def get_run(experiment_id: str, run_id: str, request: Request, view: str | None = None, db: Session = Depends(task_db)):
    if view != "task_v1" and request.headers.get("x-evalops-key"):
        actor = default_task_actor(request, db)
        c.experiment(db, actor, experiment_id)
        run = s.load(db, actor, "comparison", run_id)
        if run.experiment_id != experiment_id:
            raise HTTPException(404, "not_found")
        raise HTTPException(409, "task_view_required")
    if view != "task_v1":
        from app.api.routes_phase5 import get_experiment_run as legacy
        return legacy(experiment_id, run_id, get_current_user(request, request.headers.get("authorization"), db), db)
    actor = s.authenticate(request, db)
    c.experiment(db, actor, experiment_id)
    run = db.get(m.ExperimentRun, run_id)
    if not run or run.experiment_id != experiment_id:
        raise HTTPException(404, "not_found")
    if run.kind == "task_comparison":
        s.load(db, actor, "comparison", run.id)
        if view != "task_v1":
            raise HTTPException(409, "task_view_required")
        return {"run": s.serialize(run)}
    if view == "task_v1":
        raise HTTPException(404, "not_found")
    from app.api.routes_phase5 import get_experiment_run as legacy
    return legacy(experiment_id, run_id, get_current_user(request, request.headers.get("authorization"), db), db)


from app.domain.tasks.contracts import CaseContent, SnapshotItem
from pydantic import ValidationError


class CaseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    environment: Environment
    case: CaseContent
    source_refs: tuple[str, ...] = ()


@router.post("/datasets/{dataset_id}/cases", status_code=201)
def create_case(dataset_id: str, payload: CaseCreate, request: Request, db: Session = Depends(task_db)):
    actor = s.authenticate(request, db, "write")
    dataset = s.load(db, actor, "dataset", dataset_id, environment=payload.environment, permission="write")
    def operation():
        validate_case_content(dataset, payload.case)
        if payload.case.reference_status != "draft":
            raise HTTPException(422, "draft_case_required")
        count = db.query(m.DatasetItem).filter_by(dataset_id=dataset_id).count()
        if count >= 10000:
            raise HTTPException(422, "dataset_row_limit")
        for existing in db.query(m.DatasetItem).filter_by(dataset_id=dataset_id):
            if existing.metadata_json.get("evalops_case", {}).get("sample_id", existing.id) == payload.case.sample_id:
                raise HTTPException(409, "duplicate_sample_id")
        refs = [f"dataset:{dataset.id}", *payload.source_refs]
        label = s.derived_label(db, refs, dataset.project_id, payload.environment)
        metadata = {key: value for key, value in payload.case.metadata.items() if key not in {"evalops_case", "reference_review"}}
        metadata["evalops_case"] = {"schema_version": 1, "sample_id": payload.case.sample_id, "reference_status": "draft", "revision": 1, "source_refs": list(payload.source_refs)}
        row = m.DatasetItem(id=new_id("dti"), dataset_id=dataset_id, ord=count, input=payload.case.input,
                            expected_output=payload.case.expected_output,
                            metadata_json=metadata, access_label=label)
        db.add(row)
        return "item", row
    return s.serialize(s.write(db, actor, request, dataset.project_id, payload.model_dump(mode="json"), operation))


@router.get("/datasets/{dataset_id}/items/{item_id}")
def get_case(dataset_id: str, item_id: str, request: Request, db: Session = Depends(task_db)):
    actor = s.authenticate(request, db)
    dataset = s.load(db, actor, "dataset", dataset_id)
    row = s.load(db, actor, "item", item_id, project_id=dataset.project_id)
    if row.dataset_id != dataset_id:
        raise HTTPException(404, "not_found")
    return s.serialize(row)


class CasePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case: CaseContent
    review_reason: str | None = None


@router.patch("/datasets/{dataset_id}/cases/{item_id}")
def patch_case(dataset_id: str, item_id: str, payload: CasePatch, request: Request, db: Session = Depends(task_db)):
    actor = s.authenticate(request, db, "write")
    dataset = s.load(db, actor, "dataset", dataset_id, permission="write")
    row = s.load(db, actor, "item", item_id, project_id=dataset.project_id, permission="write")
    if row.dataset_id != dataset_id:
        raise HTTPException(404, "not_found")
    def operation():
        db.refresh(row)
        case = row.metadata_json.get("evalops_case", {})
        revision = case.get("revision", 1)
        if request.headers.get("if-match") != str(revision):
            raise HTTPException(409, "case_revision_conflict")
        if case.get("reference_status", "draft") != "draft" and (not actor.user_id or not payload.review_reason):
            raise HTTPException(403, "human_review_required")
        if payload.case.sample_id != case.get("sample_id", row.id):
            raise HTTPException(422, "sample_id_immutable")
        if payload.case.reference_status != "draft" and (not actor.user_id or not payload.review_reason):
            raise HTTPException(403, "human_review_required")
        metadata = {key: value for key, value in payload.case.metadata.items() if key not in {"evalops_case", "reference_review"}}
        metadata["evalops_case"] = {**case, "revision": revision + 1, "reference_status": payload.case.reference_status}
        if payload.case.reference_status != "draft":
            metadata["reference_review"] = {"actor_user_id": actor.user_id, "reason": payload.review_reason, "created_at": m.utcnow().isoformat()}
        validate_case_content(dataset, payload.case)
        metadata["evalops_case"]["schema_version"] = 1
        row.input = payload.case.input
        row.expected_output = payload.case.expected_output
        row.metadata_json = metadata
        from app.domain.services.audit_service import record_audit
        project = db.get(m.Project, dataset.project_id)
        record_audit(db, "task.case.updated", organization_id=project.organization_id, actor_user_id=actor.user_id,
                     target_type="item", target_id=row.id, payload={"project_id": project.id, "principal_id": actor.principal_id,
                         "revision": revision + 1, "reference_status": payload.case.reference_status, "reason": payload.review_reason})
        return "item", row
    result = s.write(db, actor, request, dataset.project_id, payload.model_dump(mode="json"), operation)
    return s.serialize(result)


def default_task_actor(request, db):
    try:
        return s.authenticate(request, db)
    except HTTPException as exc:
        if exc.status_code == 403 and exc.detail == "service_principal_required":
            raise HTTPException(401, "unauthorized") from None
        raise


def validate_case_content(dataset, case):
    if dataset.task_type == "classification":
        try:
            SnapshotContent(task_schema=dataset.task_schema, items=[case.model_dump(mode="json")])
        except ValueError:
            raise HTTPException(422, "invalid_classification_reference") from None
    if dataset.task_type == "regression":
        try:
            SnapshotItem.model_validate(case.model_dump(mode="json"))
        except ValidationError:
            raise HTTPException(422, "invalid_regression_reference") from None
