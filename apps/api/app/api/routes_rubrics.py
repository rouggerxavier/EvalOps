from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import ensure_org_membership, get_current_user
from app.domain.rubrics.parser import parse_rubric_yaml
from app.models import EvaluatorRow, Project, Rubric, RubricVersion, User
from app.schemas import RubricCreate, RubricOut, RubricVersionCreate, RubricVersionOut
from app.security import new_id

router = APIRouter(prefix="/v1")


def _persist_evaluators(db: Session, rubric_version_id: str, parsed_spec: dict) -> None:
    evaluators_spec: list[dict] = parsed_spec.get("evaluators", [])
    for idx, ev in enumerate(evaluators_spec):
        if not ev.get("enabled", True):
            continue
        row = EvaluatorRow(
            id=new_id("evl"),
            rubric_version_id=rubric_version_id,
            slug=ev["id"],
            name=ev.get("name"),
            type=ev["type"],
            config=ev.get("config", {}),
            weight=float(ev.get("weight", 1.0)),
            fail_fast=bool(ev.get("fail_fast", False)),
            enabled=True,
            ord=idx,
        )
        db.add(row)


@router.get("/projects/{project_id}/rubrics")
def list_rubrics(
    project_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    project = db.get(Project, project_id)
    if not project or project.archived_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    ensure_org_membership(db, user.id, project.organization_id)
    rubrics = db.query(Rubric).filter(Rubric.project_id == project_id).order_by(Rubric.created_at.desc()).all()
    return {"data": [RubricOut.model_validate(r).model_dump() for r in rubrics]}


@router.post("/projects/{project_id}/rubrics", status_code=status.HTTP_201_CREATED)
def create_rubric(
    project_id: str,
    payload: RubricCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    project = db.get(Project, project_id)
    if not project or project.archived_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    ensure_org_membership(db, user.id, project.organization_id)

    try:
        spec = parse_rubric_yaml(payload.yaml_source)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    existing = (
        db.query(Rubric)
        .filter(Rubric.project_id == project_id, Rubric.slug == spec.slug)
        .one_or_none()
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="rubric_slug_taken")

    rubric = Rubric(
        id=new_id("rub"),
        project_id=project_id,
        slug=spec.slug,
        description=spec.description,
        current_version=1,
        threshold=spec.threshold,
    )
    db.add(rubric)
    db.flush()

    parsed_dict = spec.model_dump()
    rubric_ver = RubricVersion(
        id=new_id("rvr"),
        rubric_id=rubric.id,
        version=1,
        yaml_source=payload.yaml_source,
        parsed_spec=parsed_dict,
        created_by=user.id,
    )
    db.add(rubric_ver)
    db.flush()

    _persist_evaluators(db, rubric_ver.id, parsed_dict)
    db.commit()
    db.refresh(rubric)
    db.refresh(rubric_ver)

    return {
        "rubric": RubricOut.model_validate(rubric).model_dump(),
        "version": RubricVersionOut.model_validate(rubric_ver).model_dump(),
    }


@router.get("/rubrics/{rubric_id}")
def get_rubric(
    rubric_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    rubric = db.get(Rubric, rubric_id)
    if not rubric:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    project = db.get(Project, rubric.project_id)
    ensure_org_membership(db, user.id, project.organization_id)
    return RubricOut.model_validate(rubric).model_dump()


@router.get("/rubrics/{rubric_id}/versions")
def list_rubric_versions(
    rubric_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    rubric = db.get(Rubric, rubric_id)
    if not rubric:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    project = db.get(Project, rubric.project_id)
    ensure_org_membership(db, user.id, project.organization_id)
    versions = (
        db.query(RubricVersion)
        .filter(RubricVersion.rubric_id == rubric_id)
        .order_by(RubricVersion.version.asc())
        .all()
    )
    return {"data": [RubricVersionOut.model_validate(v).model_dump() for v in versions]}


@router.get("/rubrics/{rubric_id}/versions/{version_num}")
def get_rubric_version(
    rubric_id: str,
    version_num: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    rubric = db.get(Rubric, rubric_id)
    if not rubric:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    project = db.get(Project, rubric.project_id)
    ensure_org_membership(db, user.id, project.organization_id)
    ver = (
        db.query(RubricVersion)
        .filter(RubricVersion.rubric_id == rubric_id, RubricVersion.version == version_num)
        .one_or_none()
    )
    if not ver:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    return RubricVersionOut.model_validate(ver).model_dump()


@router.post("/rubrics/{rubric_id}/versions", status_code=status.HTTP_201_CREATED)
def create_rubric_version(
    rubric_id: str,
    payload: RubricVersionCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    rubric = db.get(Rubric, rubric_id)
    if not rubric:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    project = db.get(Project, rubric.project_id)
    ensure_org_membership(db, user.id, project.organization_id)

    try:
        spec = parse_rubric_yaml(payload.yaml_source)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    new_version_num = rubric.current_version + 1
    parsed_dict = spec.model_dump()
    rubric_ver = RubricVersion(
        id=new_id("rvr"),
        rubric_id=rubric_id,
        version=new_version_num,
        yaml_source=payload.yaml_source,
        parsed_spec=parsed_dict,
        created_by=user.id,
    )
    db.add(rubric_ver)
    db.flush()

    _persist_evaluators(db, rubric_ver.id, parsed_dict)

    rubric.current_version = new_version_num
    rubric.threshold = spec.threshold
    db.add(rubric)
    db.commit()
    db.refresh(rubric_ver)

    return {"version": RubricVersionOut.model_validate(rubric_ver).model_dump(), "rubric_version": new_version_num}
