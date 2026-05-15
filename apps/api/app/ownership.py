"""Ownership / access helpers.

Centralises the project/trace/prompt/dataset/experiment/rubric/export
look-ups that routers used to inline. Each helper enforces membership in
the owning organisation and raises HTTP 404 ``not_found`` for missing or
archived rows so we never leak existence.

Two forms are provided:

  * ``load_*`` plain functions ``(db, user_id, <id>) -> Model`` for the
    handful of places where the id is in the request body (POST payload)
    rather than the URL path.
  * ``get_owned_*`` FastAPI dependencies suitable for ``Depends(...)``.
    They pull ``user`` from :func:`app.deps.get_current_user` and ``db``
    from :func:`app.db.get_db`, then delegate to the matching ``load_*``.

Keeping both forms in one module removes the per-router copies of
``_project_or_404`` / ``_trace_or_404`` / etc. and is the single place
where ownership rules live.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import ensure_org_membership, get_current_user
from app.models import (
    Dataset,
    Experiment,
    ExportJob,
    Project,
    Prompt,
    Rubric,
    Trace,
    User,
)


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")


# ── Plain loaders ─────────────────────────────────────────────────────────────

def load_project(db: Session, user_id: str, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if not project or project.archived_at is not None:
        raise _not_found()
    ensure_org_membership(db, user_id, project.organization_id)
    return project


def load_trace(db: Session, user_id: str, trace_id: str) -> Trace:
    trace = db.get(Trace, trace_id)
    if not trace or trace.deleted_at is not None:
        raise _not_found()
    ensure_org_membership(db, user_id, trace.organization_id)
    return trace


def load_prompt(db: Session, user_id: str, prompt_id: str) -> Prompt:
    prompt = db.get(Prompt, prompt_id)
    if not prompt:
        raise _not_found()
    load_project(db, user_id, prompt.project_id)
    return prompt


def load_dataset(db: Session, user_id: str, dataset_id: str) -> Dataset:
    dataset = db.get(Dataset, dataset_id)
    if not dataset:
        raise _not_found()
    load_project(db, user_id, dataset.project_id)
    return dataset


def load_experiment(db: Session, user_id: str, experiment_id: str) -> Experiment:
    experiment = db.get(Experiment, experiment_id)
    if not experiment:
        raise _not_found()
    load_project(db, user_id, experiment.project_id)
    return experiment


def load_rubric(db: Session, user_id: str, rubric_id: str) -> Rubric:
    rubric = db.get(Rubric, rubric_id)
    if not rubric:
        raise _not_found()
    load_project(db, user_id, rubric.project_id)
    return rubric


def load_export(db: Session, user_id: str, export_id: str) -> tuple[ExportJob, Project]:
    job = db.get(ExportJob, export_id)
    if not job:
        raise _not_found()
    project = load_project(db, user_id, job.project_id)
    return job, project


# ── FastAPI dependencies ──────────────────────────────────────────────────────

def get_owned_project(
    project_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Project:
    return load_project(db, user.id, project_id)


def get_owned_trace(
    trace_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Trace:
    return load_trace(db, user.id, trace_id)


def get_owned_prompt(
    prompt_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Prompt:
    return load_prompt(db, user.id, prompt_id)


def get_owned_dataset(
    dataset_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dataset:
    return load_dataset(db, user.id, dataset_id)


def get_owned_experiment(
    experiment_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Experiment:
    return load_experiment(db, user.id, experiment_id)


def get_owned_rubric(
    rubric_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Rubric:
    return load_rubric(db, user.id, rubric_id)
