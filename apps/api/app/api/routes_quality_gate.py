from fastapi import APIRouter, Depends, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.domain.services.audit_service import record_audit
from app.domain.services.quality_gate_service import calculate_status, get_config
from app.models import Project, QualityGateConfig, User, utcnow
from app.ownership import get_owned_project
from app.schemas import QualityGateConfigOut, QualityGateSettings, QualityGateStatusOut

router = APIRouter(prefix="/v1/projects/{project_id}/quality-gate")


@router.get("", response_model=QualityGateConfigOut)
def get_quality_gate(project: Project = Depends(get_owned_project), db: Session = Depends(get_db)):
    return get_config(db, project.id)


@router.put("", response_model=QualityGateConfigOut)
def put_quality_gate(
    payload: QualityGateSettings,
    project: Project = Depends(get_owned_project),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    values = payload.model_dump()
    config = db.query(QualityGateConfig).filter_by(project_id=project.id).with_for_update().one_or_none()
    if config is None:
        try:
            with db.begin_nested():
                config = QualityGateConfig(project_id=project.id, **values)
                db.add(config)
                db.flush()
        except IntegrityError:
            # Concurrent first PUTs must preserve one row per project.
            config = db.query(QualityGateConfig).filter_by(project_id=project.id).with_for_update().one()
    for key, value in values.items():
        setattr(config, key, value)
    config.updated_at = utcnow()
    record_audit(db, "quality_gate.updated", organization_id=project.organization_id, actor_user_id=user.id,
                 target_type="project", target_id=project.id, payload=values)
    db.commit()
    return get_config(db, project.id)


@router.get("/status", response_model=QualityGateStatusOut)
def get_quality_gate_status(
    window: str = Query(default="7d", pattern="^(24h|7d|30d)$"),
    environment: str | None = Query(default=None, max_length=16),
    project: Project = Depends(get_owned_project),
    db: Session = Depends(get_db),
):
    return calculate_status(db, project.id, window, environment)
