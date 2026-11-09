"""Ownership / access helpers.

Centralises the project/trace/prompt/dataset/experiment/rubric/export
look-ups that routers used to inline. Each helper enforces membership in
the owning organisation and raises HTTP 404 ``not_found`` for missing or
archived rows so we never leak existence.

Two forms are provided:

  * ``load_*`` plain functions ``(db, user_id, <id>) -> Model`` for the
    handful of places where the id is in the request body (POST payload)
    rather than the URL path. The project, trace, prompt and rubric loaders
    also take an API key's project in place of ``user_id`` and then only
    reach rows of that project.
  * ``get_owned_*`` FastAPI dependencies suitable for ``Depends(...)``.
    They pull ``user`` from :func:`app.deps.get_current_user` and ``db``
    from :func:`app.db.get_db`, then delegate to the matching ``load_*``.

Keeping both forms in one module removes the per-router copies of
``_project_or_404`` / ``_trace_or_404`` / etc. and is the single place
where ownership rules live.
"""
from __future__ import annotations

from typing import Callable

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import authenticate_api_key, ensure_org_membership, get_current_user
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


# Who is asking: a member's user id, or the project an API key belongs to.
Actor = str | Project


# ── Plain loaders ─────────────────────────────────────────────────────────────

def load_project(db: Session, actor: Actor, project_id: str, permission: str = "read") -> Project:
    if isinstance(actor, Project):
        if actor.id != project_id:
            raise _not_found()
        return actor
    project = db.get(Project, project_id)
    if not project or project.archived_at is not None:
        raise _not_found()
    ensure_org_membership(db, actor, project.organization_id, permission)
    return project


def load_trace(db: Session, actor: Actor, trace_id: str, permission: str = "read") -> Trace:
    trace = db.get(Trace, trace_id)
    if not trace or trace.deleted_at is not None:
        raise _not_found()
    if isinstance(actor, Project):
        if trace.project_id != actor.id:
            raise _not_found()
    else:
        ensure_org_membership(db, actor, trace.organization_id, permission)
    return trace


def load_prompt(db: Session, actor: Actor, prompt_id: str, permission: str = "read") -> Prompt:
    prompt = db.get(Prompt, prompt_id)
    if not prompt:
        raise _not_found()
    load_project(db, actor, prompt.project_id, permission)
    return prompt


def load_dataset(db: Session, user_id: str, dataset_id: str, permission: str = "read") -> Dataset:
    dataset = db.get(Dataset, dataset_id)
    if not dataset:
        raise _not_found()
    load_project(db, user_id, dataset.project_id, permission)
    return dataset


def load_experiment(db: Session, user_id: str, experiment_id: str, permission: str = "read") -> Experiment:
    experiment = db.get(Experiment, experiment_id)
    if not experiment:
        raise _not_found()
    load_project(db, user_id, experiment.project_id, permission)
    return experiment


def load_rubric(db: Session, actor: Actor, rubric_id: str, permission: str = "read") -> Rubric:
    rubric = db.get(Rubric, rubric_id)
    if not rubric:
        raise _not_found()
    load_project(db, actor, rubric.project_id, permission)
    return rubric


def load_export(db: Session, user_id: str, export_id: str, permission: str = "read") -> tuple[ExportJob, Project]:
    job = db.get(ExportJob, export_id)
    if not job:
        raise _not_found()
    project = load_project(db, user_id, job.project_id, permission)
    return job, project


# ── FastAPI dependencies ──────────────────────────────────────────────────────

def get_owned_project(
    project_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Project:
    return load_project(db, user.id, project_id)


def actor_access(scope: str | None) -> Callable[..., Actor]:
    """JWT identity, or a scoped API key; ``None`` keeps an endpoint JWT-only.

    A scope is never a role: loaders check JWT permissions against Membership.
    """

    def dependency(
        request: Request,
        x_evalops_key: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
        db: Session = Depends(get_db),
    ) -> Actor:
        if scope is not None and x_evalops_key:
            return authenticate_api_key(request, x_evalops_key, db, scope)
        return get_current_user(request, authorization, db).id

    return dependency


def project_access(scope: str | None, permission: str = "read") -> Callable[..., Project]:
    """Project from the URL, for a member or for an API key of that project with ``scope``."""

    def dependency(
        project_id: str,
        actor: Actor = Depends(actor_access(scope)),
        db: Session = Depends(get_db),
    ) -> Project:
        return load_project(db, actor, project_id, permission)

    return dependency


def trace_access(scope: str | None, permission: str = "read") -> Callable[..., Trace]:
    """Trace from the URL, for a member or for an API key of its project with ``scope``."""

    def dependency(
        trace_id: str,
        actor: Actor = Depends(actor_access(scope)),
        db: Session = Depends(get_db),
    ) -> Trace:
        return load_trace(db, actor, trace_id, permission)

    return dependency


def rubric_access(scope: str | None, permission: str = "read") -> Callable[..., Rubric]:
    """Rubric from the URL, for a member or for an API key of its project with ``scope``."""

    def dependency(
        rubric_id: str,
        actor: Actor = Depends(actor_access(scope)),
        db: Session = Depends(get_db),
    ) -> Rubric:
        return load_rubric(db, actor, rubric_id, permission)

    return dependency


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
