"""JWT-only read previews; no API-key fallback or deletion execution."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.schemas_deletion_preview import DeletionPreview
from app.db import get_db
from app.deps import ensure_org_membership, get_current_user
from app.domain.services.deletion_preview_service import account_preview, content_preview
from app.models import Organization, Project, User

router = APIRouter(prefix="/v1", tags=["deletion-preview"])


@router.get("/projects/{project_id}/deletion-preview", response_model=DeletionPreview)
def project_deletion_preview(project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="not_found")
    try:
        ensure_org_membership(db, user.id, project.organization_id, "destructive")
    except HTTPException as exc:
        if project.archived_at is not None:  # load_project convention: archived is not_found below owner
            raise HTTPException(status_code=404, detail="not_found") from exc
        raise
    return content_preview(db, scope="project", target_id=project_id, organization_id=project.organization_id)


@router.get("/organizations/{org_id}/deletion-preview", response_model=DeletionPreview)
def organization_deletion_preview(org_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_org_membership(db, user.id, org_id, "destructive")
    if db.get(Organization, org_id) is None:
        raise HTTPException(status_code=404, detail="not_found")
    return content_preview(db, scope="organization", target_id=org_id, organization_id=org_id)


@router.get("/auth/me/deletion-preview", response_model=DeletionPreview)
def personal_deletion_preview(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return account_preview(db, user)
