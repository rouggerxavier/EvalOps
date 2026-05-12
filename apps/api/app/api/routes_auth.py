"""Authentication routes: register, login, logout, session info.

Implements a minimal MVP password-based auth flow on top of the existing
JWT bearer system. On register, a default organization and project are
created so the user lands directly in a usable workspace.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import Membership, Organization, Project, User
from app.security import (
    create_session_token,
    hash_password,
    new_id,
    verify_password,
)

router = APIRouter(prefix="/v1/auth", tags=["auth"])


SLUG_RE = re.compile(r"[^a-z0-9-]+")


def _slugify(value: str) -> str:
    base = re.sub(r"\s+", "-", value.strip().lower())
    base = SLUG_RE.sub("", base)
    base = re.sub(r"-+", "-", base).strip("-")
    return base[:48] or "workspace"


def _unique_slug(db: Session, *, kind: str, base: str, org_id: str | None = None) -> str:
    candidate = base
    suffix = 2
    while True:
        if kind == "org":
            taken = db.query(Organization).filter(Organization.slug == candidate).first()
        else:
            taken = (
                db.query(Project)
                .filter(Project.organization_id == org_id, Project.slug == candidate)
                .first()
            )
        if taken is None:
            return candidate
        candidate = f"{base}-{suffix}"
        suffix += 1


EMAIL_RE_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320, pattern=EMAIL_RE_PATTERN)
    name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8, max_length=256)
    org_name: str | None = Field(default=None, max_length=255)
    project_name: str | None = Field(default=None, max_length=255)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320, pattern=EMAIL_RE_PATTERN)
    password: str = Field(min_length=1, max_length=256)


class WorkspaceOut(BaseModel):
    org_id: str
    org_slug: str
    org_name: str
    project_id: str
    project_slug: str
    project_name: str


class AuthResponse(BaseModel):
    token: str
    user: dict
    workspace: WorkspaceOut | None = None


def _user_dict(user: User) -> dict:
    return {"id": user.id, "email": user.email, "name": user.name}


def _default_workspace_for_user(db: Session, user: User) -> WorkspaceOut | None:
    membership = (
        db.query(Membership)
        .filter(Membership.user_id == user.id)
        .order_by(Membership.created_at.asc())
        .first()
    )
    if membership is None:
        return None
    org = db.get(Organization, membership.organization_id)
    if org is None:
        return None
    project = (
        db.query(Project)
        .filter(Project.organization_id == org.id, Project.archived_at.is_(None))
        .order_by(Project.created_at.asc())
        .first()
    )
    if project is None:
        return None
    return WorkspaceOut(
        org_id=org.id,
        org_slug=org.slug,
        org_name=org.name,
        project_id=project.id,
        project_slug=project.slug,
        project_name=project.name,
    )


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=AuthResponse)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> AuthResponse:
    email = payload.email.lower().strip()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="email_taken")

    user = User(
        id=new_id("usr"),
        email=email,
        name=payload.name.strip(),
        password_hash=hash_password(payload.password),
    )
    db.add(user)

    org_display = (payload.org_name or f"{user.name}'s Workspace").strip()
    org_slug = _unique_slug(db, kind="org", base=_slugify(org_display))
    org = Organization(id=new_id("org"), name=org_display, slug=org_slug)
    db.add(org)
    db.flush()

    db.add(Membership(user_id=user.id, organization_id=org.id, role="owner"))

    project_display = (payload.project_name or "Default project").strip()
    project_slug = _unique_slug(
        db, kind="project", base=_slugify(project_display), org_id=org.id
    )
    project = Project(
        id=new_id("prj"),
        organization_id=org.id,
        name=project_display,
        slug=project_slug,
        description=None,
    )
    db.add(project)
    db.commit()
    db.refresh(user)
    db.refresh(org)
    db.refresh(project)

    token = create_session_token(sub=user.id, email=user.email, name=user.name)
    workspace = WorkspaceOut(
        org_id=org.id,
        org_slug=org.slug,
        org_name=org.name,
        project_id=project.id,
        project_slug=project.slug,
        project_name=project.name,
    )
    return AuthResponse(token=token, user=_user_dict(user), workspace=workspace)


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> AuthResponse:
    email = payload.email.lower().strip()
    user = db.query(User).filter(User.email == email).first()
    if user is None or not user.password_hash or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_credentials")
    token = create_session_token(sub=user.id, email=user.email, name=user.name)
    workspace = _default_workspace_for_user(db, user)
    return AuthResponse(token=token, user=_user_dict(user), workspace=workspace)


@router.get("/session", response_model=AuthResponse)
def session(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> AuthResponse:
    workspace = _default_workspace_for_user(db, user)
    return AuthResponse(token="", user=_user_dict(user), workspace=workspace)
