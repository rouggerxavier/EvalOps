"""Transactional offline task services shared by HTTP clients and the web."""
from dataclasses import dataclass
from datetime import datetime
from app.timestamps import server_timestamp

from fastapi import HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, object_session

from app import models as m
from app.deps import authenticate_api_key, get_current_user, ensure_org_membership
from app.domain.services.audit_service import record_audit
from app.domain.tasks.access import AccessDenied, Source, authorize_sources
from app.domain.tasks.contracts import (
    AccessLabel, SnapshotContent, SnapshotItem, PredictionRow, digest, canonical_json,
)
from app.domain.tasks.regression import evaluate_task
from app.ownership import load_project
from app.security import new_id


@dataclass(frozen=True)
class TaskActor:
    user_id: str | None
    project_id: str | None
    principal_id: str | None
    environment: str | None
    scopes: frozenset[str]

    @property
    def id(self):
        return self.principal_id or self.user_id


def authenticate(request: Request, db: Session, scope: str = "read") -> TaskActor:
    key = request.headers.get("x-evalops-key")
    if key:
        request.state.task_surface = True
        project = authenticate_api_key(request, key, db, scope, require_service_principal=True)
        if not request.state.service_principal_id:
            raise HTTPException(403, "service_principal_required")
        return TaskActor(None, project.id, request.state.service_principal_id,
                         request.state.key_environment, frozenset(request.state.key_scopes))
    user = get_current_user(request, request.headers.get("authorization"), db)
    return TaskActor(user.id, None, None, None, frozenset())


def project_access(db, actor, project_id, permission="read"):
    if actor.project_id:
        if permission in {"admin", "destructive"}:
            raise HTTPException(403, "forbidden")
        if actor.project_id != project_id:
            raise HTTPException(404, "not_found")
        required = "write" if permission == "write" else "evaluate" if permission == "evaluate" else "read"
        if required not in actor.scopes or "read" not in actor.scopes:
            raise HTTPException(403, "forbidden")
        project = db.get(m.Project, project_id)
        if not project or project.archived_at is not None:
            raise HTTPException(404, "not_found")
        return project
    return load_project(db, actor.user_id, project_id, "write" if permission == "evaluate" else permission)


RESOURCE_MODELS = {
    "dataset": m.Dataset, "item": m.DatasetItem, "snapshot": m.DatasetSnapshot,
    "model": m.ModelVersion, "predictions": m.PredictionSet, "evaluation": m.TaskEvaluation,
    "investigation": m.Investigation, "investigation_revision": m.InvestigationRevision, "trace": m.Trace,
    "principal": m.ServicePrincipal, "comparison": m.ExperimentRun, "experiment": m.Experiment,
}


def source_for(db, ref):
    cache = db.info.setdefault("task_sources", {})
    if ref not in cache:
        pending, visited = [ref], set()
        dataset_projects = db.info.setdefault("task_dataset_projects", {})
        while pending:
            grouped = {}
            for current in pending:
                if current in visited or current in cache:
                    continue
                visited.add(current)
                try:
                    kind, identifier = current.split(":", 1)
                except ValueError:
                    raise AccessDenied("not_found") from None
                if kind not in RESOURCE_MODELS:
                    raise AccessDenied("not_found")
                grouped.setdefault(kind, []).append(identifier)
            pending = []
            for kind, identifiers in grouped.items():
                model = RESOURCE_MODELS[kind]
                for offset in range(0, len(identifiers), 500):
                    rows = db.query(model).filter(model.id.in_(identifiers[offset:offset + 500])).populate_existing().all()
                    if kind == "item":
                        missing = {row.dataset_id for row in rows} - dataset_projects.keys()
                        if missing:
                            dataset_projects.update(dict(db.query(m.Dataset.id, m.Dataset.project_id).filter(m.Dataset.id.in_(missing)).all()))
                    for row in rows:
                        project_id = dataset_projects.get(row.dataset_id) if kind == "item" else row.project_id
                        raw = row.run_metadata.get("access_label") if kind == "comparison" else row.pass_criteria.get("access_label") if kind == "experiment" else getattr(row, "access_label", None)
                        if kind == "trace":
                            if row.deleted_at is not None or row.environment not in {"dev", "staging", "prod"}:
                                continue
                            raw = AccessLabel(origin_environments=(row.environment,), allowed_environments=(row.environment,)).model_dump(mode="json")
                        label = AccessLabel.model_validate(raw) if raw else None
                        environment = row.run_metadata.get("environment") if kind == "comparison" else row.pass_criteria.get("environment") if kind == "experiment" else getattr(row, "environment", None)
                        cache[f"{kind}:{row.id}"] = Source(project_id, label, environment)
                        if label:
                            pending.extend(label.source_refs)
    if ref not in cache:
        raise AccessDenied("not_found")
    return cache[ref]


def load(db, actor, kind, identifier, *, project_id=None, environment=None, permission="read"):
    model = RESOURCE_MODELS[kind]
    row = db.get(model, identifier)
    if row is None:
        raise HTTPException(404, "not_found")
    owning_project_id = db.get(m.Dataset, row.dataset_id).project_id if kind == "item" else row.project_id
    if project_id and owning_project_id != project_id:
        raise HTTPException(404, "not_found")
    project_access(db, actor, owning_project_id, permission)
    if actor.environment or environment or getattr(row, "access_label", None) is not None or kind in {"comparison", "experiment", "trace"}:
        try:
            authorize_sources(source_for(db, f"{kind}:{identifier}"), project_id=owning_project_id,
                              environment=actor.environment or environment, resolve=lambda ref: source_for(db, ref))
        except AccessDenied:
            raise HTTPException(404, "not_found") from None
    if permission == "read" and ("prod" in (getattr(row, "access_label", None) or {}).get("origin_environments", []) or (kind == "trace" and row.environment == "prod")):
        audit(db, actor, owning_project_id, "task.sensitive_read", f"{kind}:{row.id}")
    return row


def declare_label(db, actor, project, declaration):
    if actor.environment and declaration.environment != actor.environment:
        raise HTTPException(404, "not_found")
    allowed = declaration.allowed_environments or (declaration.environment,)
    if declaration.independent:
        if not actor.user_id:
            raise HTTPException(403, "forbidden")
        ensure_org_membership(db, actor.user_id, project.organization_id, "admin")
        if not declaration.justification or not declaration.evidence or not declaration.allowed_environments:
            raise HTTPException(422, "independent_origin_evidence_required")
        origins = ()
    else:
        if allowed != (declaration.environment,):
            raise HTTPException(422, "origin_environment_mismatch")
        origins = (declaration.environment,)
    record_audit(db, "task.origin.declared", organization_id=project.organization_id,
                 actor_user_id=actor.user_id, target_type="project", target_id=project.id,
                 payload={"principal_id": actor.principal_id, "environment": declaration.environment,
                          "independent": declaration.independent, "allowed_environments": list(allowed),
                          "justification": declaration.justification, "evidence": declaration.evidence,
                          "provenance": "declared"})
    return AccessLabel(origin_environments=origins, allowed_environments=allowed).model_dump(mode="json")


def derived_label(db, refs, project_id, environment, allowed_environments=None):
    origins, allowed = set(), set(allowed_environments or (environment,))
    for ref in refs:
        try:
            source = source_for(db, ref)
            authorize_sources(source, project_id=project_id, environment=environment, resolve=lambda value: source_for(db, value))
        except AccessDenied:
            raise HTTPException(404, "not_found") from None
        origins.update(source.label.origin_environments)
        allowed.intersection_update(source.label.allowed_environments)
    if environment not in allowed:
        raise HTTPException(404, "not_found")
    return AccessLabel(origin_environments=tuple(sorted(origins)), allowed_environments=tuple(sorted(allowed)),
                       source_refs=tuple(refs)).model_dump(mode="json")


def audit(db, actor, project_id, action, ref):
    project = db.get(m.Project, project_id)
    record_audit(db, action, organization_id=project.organization_id, actor_user_id=actor.user_id,
                 target_type=ref.split(":")[0], target_id=ref.split(":", 1)[1],
                 payload={"project_id": project_id, "principal_id": actor.principal_id, "environment": actor.environment})


def revalidate_principal(db, key_id):
    from app.deps import _is_expired
    from datetime import timezone
    key = db.query(m.ApiKey).filter_by(id=key_id).populate_existing().with_for_update().one_or_none()
    principal = db.query(m.ServicePrincipal).filter_by(id=key.service_principal_id).populate_existing().with_for_update().one_or_none() if key else None
    project = db.get(m.Project, key.project_id) if key else None
    owner = db.query(m.Membership).filter_by(user_id=principal.owner_user_id, organization_id=project.organization_id).populate_existing().with_for_update().one_or_none() if principal and project else None
    if (not key or key.revoked_at or _is_expired(key.expires_at, datetime.now(timezone.utc))
            or not principal or principal.disabled_at or not owner or owner.role != "owner"):
        raise HTTPException(401, "unauthorized")


def write(db, actor, request, project_id, payload, operation):
    key = request.headers.get("idempotency-key", "")
    if not key or len(key) > 128:
        raise HTTPException(422, "idempotency_key_required")
    # Serialize new resource writes and policy restrictions on the project row.
    db.query(m.Project).filter_by(id=project_id).update({m.Project.name: m.Project.name}, synchronize_session=False)
    db.info.pop("task_sources", None)
    db.info.pop("task_dataset_projects", None)
    db.expire_all()
    body_hash = digest(payload)
    query = db.query(m.TaskReceipt).filter_by(project_id=project_id, actor_id=actor.id,
                                             method=request.method, path=request.url.path, key=key)
    receipt = query.one_or_none()
    if receipt:
        if receipt.body_hash != body_hash:
            raise HTTPException(409, "idempotency_conflict")
        kind, identifier = receipt.resource_ref.split(":", 1)
        if kind == "principal":
            project_access(db, actor, project_id, "admin")
            return db.get(m.ServicePrincipal, identifier)
        authorized = load(db, actor, kind, identifier, project_id=project_id)
        return receipt.response_snapshot if receipt.response_snapshot is not None else authorized
    try:
        kind, row = operation()
        db.flush()
        ref = f"{kind}:{row.id}"
        db.add(m.TaskReceipt(id=new_id("receipt"), project_id=project_id, actor_id=actor.id,
                             method=request.method, path=request.url.path, key=key, body_hash=body_hash, resource_ref=ref,
                             response_snapshot=serialize(row) if kind == "item" and request.method == "PATCH" else None))
        audit(db, actor, project_id, f"task.{kind}.{'updated' if request.method == 'PATCH' else 'created'}", ref)
        db.expire_all()
        project_access(db, actor, project_id, "admin" if kind == "principal" else "evaluate" if kind in {"evaluation", "comparison"} else "write")
        if actor.principal_id:
            revalidate_principal(db, request.state.api_key_id)
        db.commit()
        return row
    except IntegrityError:
        db.rollback()
        receipt = query.one_or_none()
        if receipt and receipt.body_hash == body_hash:
            kind, identifier = receipt.resource_ref.split(":", 1)
            authorized = load(db, actor, kind, identifier, project_id=project_id)
            return receipt.response_snapshot if receipt.response_snapshot is not None else authorized
        raise HTTPException(409, "resource_conflict") from None


def create_dataset(db, actor, project_id, payload):
    project = project_access(db, actor, project_id, "write")
    label = declare_label(db, actor, project, payload.access)
    content = SnapshotContent(task_schema=payload.task_schema, items=payload.items)
    dataset = m.Dataset(id=new_id("dts"), project_id=project_id, slug=payload.slug,
                        description=payload.description, task_type="regression",
                        task_schema=payload.task_schema.model_dump(mode="json"), access_label=label)
    db.add(dataset)
    db.flush()
    for index, item in enumerate(content.items):
        if item.reference_status == "reviewed":
            raise HTTPException(422, "reference_review_requires_separate_human_review")
        metadata = dict(item.metadata)
        metadata["evalops_case"] = {"sample_id": item.sample_id, "reference_status": item.reference_status}
        db.add(m.DatasetItem(id=new_id("dti"), dataset_id=dataset.id, ord=index, input=item.input,
                             expected_output=item.expected_output.model_dump() if item.expected_output else None,
                             metadata_json=metadata, access_label=label))
    return "dataset", dataset


def create_snapshot(db, actor, dataset_id, environment, allowed_environments=None):
    dataset = load(db, actor, "dataset", dataset_id, environment=environment, permission="write")
    if dataset.task_type != "regression":
        raise HTTPException(422, "regression_dataset_required")
    items = db.query(m.DatasetItem).filter_by(dataset_id=dataset.id).order_by(m.DatasetItem.id).all()
    refs = [f"dataset:{dataset.id}"] + [f"item:{item.id}" for item in items]
    if allowed_environments is not None and (not allowed_environments or environment not in allowed_environments or len(set(allowed_environments)) != len(allowed_environments)):
        raise HTTPException(422, "invalid_snapshot_allowlist")
    if actor.environment and allowed_environments and set(allowed_environments) != {actor.environment}:
        raise HTTPException(403, "forbidden")
    label = derived_label(db, refs, dataset.project_id, environment, allowed_environments)
    copied = []
    for item in items:
        metadata = dict(item.metadata_json)
        case = metadata.pop("evalops_case", {})
        copied.append(SnapshotItem(sample_id=case.get("sample_id", item.id), input=item.input,
                                   expected_output=item.expected_output, metadata=metadata,
                                   reference_status=case.get("reference_status", "draft")))
    content = SnapshotContent(task_schema=dataset.task_schema, items=tuple(copied))
    row = m.DatasetSnapshot(id=new_id("snapshot"), project_id=dataset.project_id, dataset_id=dataset.id,
                            content_hash=content.content_hash, item_count=len(copied), content=content.materialize(),
                            access_label=label, created_by=actor.id)
    db.add(row)
    db.flush()
    for item in content.items:
        db.add(m.SnapshotItem(snapshot_id=row.id, sample_id=item.sample_id, content=item.model_dump(mode="json")))
    return "snapshot", row


def create_model(db, actor, project_id, payload):
    project = project_access(db, actor, project_id, "write")
    label = declare_label(db, actor, project, payload.access)
    existing = db.query(m.ModelVersion).filter_by(project_id=project_id, name=payload.model.name,
                                                 version_ref=payload.model.version_ref).one_or_none()
    if existing:
        load(db, actor, "model", existing.id, project_id=project_id)
        if existing.content_hash != payload.model.content_hash or existing.access_label != label:
            raise HTTPException(409, "immutable_model_version")
        return "model", existing
    row = m.ModelVersion(id=new_id("model"), project_id=project_id, name=payload.model.name,
                         version_ref=payload.model.version_ref, content_hash=payload.model.content_hash,
                         content=payload.model.model_dump(mode="json"), access_label=label)
    db.add(row)
    return "model", row


def create_predictions(db, actor, project_id, payload):
    project_access(db, actor, project_id, "write")
    if actor.environment and actor.environment != payload.environment:
        raise HTTPException(404, "not_found")
    snap = load(db, actor, "snapshot", payload.snapshot_id, project_id=project_id, environment=payload.environment)
    load(db, actor, "model", payload.model_version_id, project_id=project_id, environment=payload.environment)
    content = SnapshotContent.model_validate_json(snap.content)
    # Validate the full import before writing any rows.
    identifiers = {item.sample_id for item in content.items}
    keys = [row.sample_id for row in payload.rows]
    if len(set(keys)) != len(keys) or set(keys) - identifiers:
        raise HTTPException(422, "invalid_prediction_sample_ids")
    refs = [f"snapshot:{snap.id}", f"model:{payload.model_version_id}"]
    label = derived_label(db, refs, project_id, payload.environment)
    hashed = digest({"rows": [row.model_dump(mode="json") for row in sorted(payload.rows, key=lambda row: row.sample_id)],
                     "producer_manifest": payload.producer_manifest, "environment": payload.environment})
    existing = db.query(m.PredictionSet).filter_by(project_id=project_id, snapshot_id=snap.id,
                    model_version_id=payload.model_version_id, content_hash=hashed).one_or_none()
    if existing:
        return "predictions", load(db, actor, "predictions", existing.id, project_id=project_id)
    row = m.PredictionSet(id=new_id("predictions"), project_id=project_id, snapshot_id=snap.id,
                          model_version_id=payload.model_version_id, environment=payload.environment,
                          content_hash=hashed, producer_manifest=payload.producer_manifest, access_label=label)
    db.add(row)
    db.flush()
    for item in payload.rows:
        db.add(m.Prediction(set_id=row.id, snapshot_id=snap.id, sample_id=item.sample_id, content=item.model_dump(mode="json")))
    return "predictions", row


def create_evaluation(db, actor, project_id, payload):
    project_access(db, actor, project_id, "evaluate")
    predictions = load(db, actor, "predictions", payload.prediction_set_id, project_id=project_id)
    snap = load(db, actor, "snapshot", predictions.snapshot_id, project_id=project_id, environment=predictions.environment)
    label = derived_label(db, [f"predictions:{predictions.id}"], project_id, predictions.environment)
    rows = tuple(PredictionRow.model_validate(row.content) for row in db.query(m.Prediction).filter_by(set_id=predictions.id).all())
    result = evaluate_task(SnapshotContent.model_validate_json(snap.content), rows, payload.evaluator)
    row = m.TaskEvaluation(id=new_id("evaluation"), project_id=project_id, prediction_set_id=predictions.id,
                           environment=predictions.environment, status=result.status, decision=result.decision,
                           decision_reasons=list(result.decision_reasons), result={**result.model_dump(mode="json", exclude={"metrics"}), "snapshot_id": snap.id},
                           access_label=label, created_by=actor.id)
    db.add(row)
    db.flush()
    for fact in result.metrics:
        db.add(m.MetricFact(id=new_id("metric"), task_evaluation_id=row.id, definition_id=fact.definition_id,
                            definition_version=fact.definition_version, scope=fact.scope, scope_key=fact.scope_key,
                            content=fact.model_dump(mode="json")))
    return "evaluation", row


def serialize(row):
    if isinstance(row, dict):
        return row
    if isinstance(row, m.DatasetItem):
        case = row.metadata_json.get("evalops_case", {})
        return {"id": row.id, "dataset_id": row.dataset_id, "sample_id": case.get("sample_id", row.id),
                "input": row.input, "expected_output": row.expected_output, "metadata": row.metadata_json,
                "reference_status": case.get("reference_status", "draft"), "revision": case.get("revision", 1)}
    common = {"id": row.id, "project_id": row.project_id, "created_at": server_timestamp(row.created_at).isoformat()}
    if isinstance(row, m.Dataset):
        return {**common, "kind": "dataset", "slug": row.slug, "description": row.description,
                "task_type": row.task_type, "task_schema": row.task_schema, "access_label": row.access_label}
    if isinstance(row, m.DatasetSnapshot):
        return {**common, "kind": "dataset_snapshot", "schema_version": 1, "dataset_id": row.dataset_id,
                "content_hash": row.content_hash, "item_count": row.item_count,
                "task_schema": SnapshotContent.model_validate_json(row.content).task_schema.model_dump(mode="json"),
                "access_label": row.access_label}
    if isinstance(row, m.ModelVersion):
        return {**common, "kind": "model_version", **row.content, "content_hash": row.content_hash, "access_label": row.access_label}
    if isinstance(row, m.PredictionSet):
        return {**common, "kind": "prediction_set", "snapshot_id": row.snapshot_id,
                "model_version_id": row.model_version_id, "environment": row.environment,
                "content_hash": row.content_hash, "producer_manifest": row.producer_manifest, "provenance": row.provenance}
    if isinstance(row, m.TaskEvaluation):
        db = object_session(row)
        project = db.get(m.Project, row.project_id)
        org = db.get(m.Organization, project.organization_id)
        web_path = f"/o/{org.slug}/p/{project.slug}/evaluations/tasks/{row.id}"
        result = {key: value for key, value in row.result.items() if key != "metrics"}
        return {**common, **result, "environment": row.environment, "prediction_set_id": row.prediction_set_id,
                "decision": row.decision, "decision_reasons": row.decision_reasons,
                "error": None, "evidence_refs": [], "completed_at": server_timestamp(row.created_at).isoformat(),
                "links": {"metrics": f"/v1/task-evaluations/{row.id}/metrics",
                          "samples": f"/v1/task-evaluations/{row.id}/samples", "web": web_path}}
    if isinstance(row, (m.Investigation, m.InvestigationRevision)):
        revision = isinstance(row, m.InvestigationRevision)
        identifier = row.investigation_id if revision else row.id
        db = object_session(row)
        current = db.get(m.Investigation, identifier) if revision else row
        author = row if revision else db.query(m.InvestigationRevision).filter_by(investigation_id=identifier, revision=row.revision).one()
        return {**common, "id": identifier, "kind": "investigation", "schema_version": 1,
                "environment": row.environment, "revision": row.revision, **row.state,
                "author_kind": author.author_kind,
                "author_id": author.author_id,
                "revision_id": author.id, "created_at": server_timestamp(current.created_at).isoformat(),
                "updated_at": server_timestamp(author.created_at).isoformat()}
    if isinstance(row, m.ServicePrincipal):
        return {**common, "name": row.name, "owner_user_id": row.owner_user_id,
                "disabled_at": server_timestamp(row.disabled_at).isoformat() if row.disabled_at else None}
    if isinstance(row, m.Experiment):
        return {**common, "schema_version": 1, "kind": row.kind, "name": row.name,
                "dataset_id": row.dataset_id, "snapshot_id": row.snapshot_id, "rubric_id": None,
                "environment": row.pass_criteria.get("environment"), "variants": row.variants}
    if isinstance(row, m.ExperimentRun):
        metadata = {key: value for key, value in row.run_metadata.items() if key != "access_label"}
        return {**common, **metadata, "kind": "task_comparison", "experiment_id": row.experiment_id,
                "status": row.status, "decision": row.decision, "decision_reasons": row.decision_reasons,
                "evidence_refs": [], "started_at": server_timestamp(row.started_at).isoformat(),
                "completed_at": server_timestamp(row.completed_at).isoformat()}
    raise TypeError(type(row))
