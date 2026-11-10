"""Resumable investigations with immutable revisions and cumulative source restrictions."""
from typing import Annotated, Literal

from fastapi import HTTPException
from pydantic import Field
from sqlalchemy.orm import Session

from app import models as m
from app.domain.tasks import service as s
from app.domain.tasks.access import AccessDenied
from app.domain.tasks.contracts import Contract, Environment
from app.security import new_id


ShortText = Annotated[str, Field(min_length=1, max_length=2000)]
Reference = Annotated[str, Field(min_length=1, max_length=128)]


class InvestigationState(Contract):
    title: str = Field(min_length=1, max_length=255)
    status: Literal["open", "resolved"] = "open"
    summary: str = Field(default="", max_length=10000)
    hypotheses: tuple[ShortText, ...] = Field(default=(), max_length=50)
    evidence_refs: tuple[Reference, ...] = Field(default=(), max_length=100)
    run_ids: tuple[Reference, ...] = Field(default=(), max_length=50)
    next_steps: tuple[ShortText, ...] = Field(default=(), max_length=50)
    decision: Literal["pass", "fail", "review", "inconclusive"] | None = None


class InvestigationCreate(Contract):
    environment: Environment
    state: InvestigationState


class InvestigationPatch(Contract):
    state: InvestigationState


def references(db, state):
    refs = list(state.evidence_refs)
    allowed = {"dataset", "item", "trace", "snapshot", "model", "predictions", "evaluation", "comparison"}
    for ref in refs:
        if ref.split(":", 1)[0] not in allowed or ":" not in ref:
            raise HTTPException(422, "invalid_evidence_reference")
    for identifier in state.run_ids:
        if db.get(m.TaskEvaluation, identifier):
            refs.append(f"evaluation:{identifier}")
        elif (run := db.get(m.ExperimentRun, identifier)) and run.kind == "task_comparison":
            refs.append(f"comparison:{identifier}")
        else:
            raise HTTPException(404, "not_found")
    return list(dict.fromkeys(refs))


def reject_cycle(db, refs, identifier):
    pending, checked = list(refs), set()
    while pending:
        ref = pending.pop()
        if ref == f"investigation:{identifier}":
            raise HTTPException(422, "cyclic_evidence")
        if ref in checked:
            continue
        checked.add(ref)
        try:
            source = s.source_for(db, ref)
        except AccessDenied:
            raise HTTPException(404, "not_found") from None
        if source.label:
            pending.extend(source.label.source_refs)


def revise(db: Session, actor, project_id, state, environment, identifier=None, expected_revision=None):
    s.project_access(db, actor, project_id, "write")
    if actor.environment and environment != actor.environment:
        raise HTTPException(404, "not_found")
    now = m.utcnow()
    refs = references(db, state)
    if identifier:
        current = s.load(db, actor, "investigation", identifier, project_id=project_id, permission="write")
        db.refresh(current)
        if current.revision != expected_revision:
            raise HTTPException(409, "investigation_revision_conflict")
        refs = list(dict.fromkeys([*current.access_label["source_refs"], *refs]))
        if len(refs) > 500:
            raise HTTPException(422, "investigation_source_limit")
        reject_cycle(db, refs, identifier)
        label = s.derived_label(db, refs, project_id, environment)
        # Saved restrictions never widen when a reference disappears from the current editor.
        label["allowed_environments"] = sorted(set(label["allowed_environments"]) & set(current.access_label["allowed_environments"]))
        if environment not in label["allowed_environments"]:
            raise HTTPException(404, "not_found")
        label["origin_environments"] = sorted(set(label["origin_environments"]) | set(current.access_label["origin_environments"]))
        revision = current.revision + 1
        count = db.query(m.Investigation).filter_by(id=identifier, revision=expected_revision).update({
            "revision": revision, "state": state.model_dump(mode="json"), "access_label": label, "updated_at": now,
        }, synchronize_session=False)
        if count != 1:
            raise HTTPException(409, "investigation_revision_conflict")
    else:
        revision = 1
        label = s.derived_label(db, refs, project_id, environment) if refs else {
            "label_schema_version": 1, "access_revision": 1, "origin_environments": [environment],
            "allowed_environments": [environment], "source_refs": [],
        }
        current = m.Investigation(id=new_id("investigation"), project_id=project_id, environment=environment,
                                 revision=1, state=state.model_dump(mode="json"), access_label=label, created_at=now, updated_at=now)
        db.add(current); db.flush()
        identifier = current.id
    row = m.InvestigationRevision(id=new_id("invrev"), investigation_id=identifier, project_id=project_id,
        environment=environment, revision=revision, state=state.model_dump(mode="json"),
        access_label={**label, "source_refs": [f"investigation:{identifier}"]},
        author_kind="service" if actor.principal_id else "human", author_id=actor.id, created_at=now)
    db.add(row)
    return "investigation_revision", row
