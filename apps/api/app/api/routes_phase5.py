from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import ensure_org_membership, get_current_user
from app.domain.services.experiment_service import (
    ExperimentValidationError,
    execute_experiment,
    validate_variants,
)
from app.models import (
    Dataset,
    DatasetItem,
    Experiment,
    ExperimentRun,
    Project,
    Prompt,
    PromptVersion,
    Rubric,
    Span,
    Trace,
    User,
    utcnow,
)
from app.schemas import (
    DatasetBuildFromTraces,
    DatasetCreate,
    DatasetItemOut,
    DatasetItemsCreate,
    DatasetOut,
    ExperimentCreate,
    ExperimentOut,
    ExperimentRunOut,
    ExperimentRunRequest,
    PromptCreate,
    PromptOut,
    PromptVersionCreate,
    PromptVersionOut,
)
from app.security import new_id

router = APIRouter(prefix="/v1")


def _project_or_404(project_id: str, user_id: str, db: Session) -> Project:
    project = db.get(Project, project_id)
    if not project or project.archived_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    ensure_org_membership(db, user_id, project.organization_id)
    return project


def _prompt_or_404(prompt_id: str, user_id: str, db: Session) -> Prompt:
    prompt = db.get(Prompt, prompt_id)
    if not prompt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    project = db.get(Project, prompt.project_id)
    if not project or project.archived_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    ensure_org_membership(db, user_id, project.organization_id)
    return prompt


def _dataset_or_404(dataset_id: str, user_id: str, db: Session) -> Dataset:
    dataset = db.get(Dataset, dataset_id)
    if not dataset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    project = db.get(Project, dataset.project_id)
    if not project or project.archived_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    ensure_org_membership(db, user_id, project.organization_id)
    return dataset


def _experiment_or_404(experiment_id: str, user_id: str, db: Session) -> Experiment:
    experiment = db.get(Experiment, experiment_id)
    if not experiment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    project = db.get(Project, experiment.project_id)
    if not project or project.archived_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    ensure_org_membership(db, user_id, project.organization_id)
    return experiment


@router.get("/projects/{project_id}/prompts")
def list_prompts(
    project_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    _project_or_404(project_id, user.id, db)
    rows = db.query(Prompt).filter(Prompt.project_id == project_id).order_by(Prompt.created_at.desc()).all()
    return {"data": [PromptOut.model_validate(row).model_dump() for row in rows]}


@router.post("/projects/{project_id}/prompts", status_code=status.HTTP_201_CREATED)
def create_prompt(
    project_id: str,
    payload: PromptCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    _project_or_404(project_id, user.id, db)
    existing = (
        db.query(Prompt)
        .filter(Prompt.project_id == project_id, Prompt.slug == payload.slug)
        .one_or_none()
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="prompt_slug_taken")

    prompt = Prompt(
        id=new_id("pmt"),
        project_id=project_id,
        slug=payload.slug,
        description=payload.description,
        current_version=1,
    )
    db.add(prompt)
    db.flush()

    version = PromptVersion(
        id=new_id("pmv"),
        prompt_id=prompt.id,
        version=1,
        template=payload.template,
        variables=payload.variables,
        metadata_json=payload.metadata,
        changelog=payload.changelog,
        created_by=user.id,
    )
    db.add(version)
    db.commit()
    db.refresh(prompt)
    db.refresh(version)
    return {
        "prompt": PromptOut.model_validate(prompt).model_dump(),
        "version": PromptVersionOut.model_validate(version).model_dump(),
    }


@router.get("/prompts/{prompt_id}")
def get_prompt(
    prompt_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    prompt = _prompt_or_404(prompt_id, user.id, db)
    return PromptOut.model_validate(prompt).model_dump()


@router.get("/prompts/{prompt_id}/versions")
def list_prompt_versions(
    prompt_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    _prompt_or_404(prompt_id, user.id, db)
    rows = (
        db.query(PromptVersion)
        .filter(PromptVersion.prompt_id == prompt_id)
        .order_by(PromptVersion.version.asc())
        .all()
    )
    return {"data": [PromptVersionOut.model_validate(row).model_dump() for row in rows]}


@router.post("/prompts/{prompt_id}/versions", status_code=status.HTTP_201_CREATED)
def create_prompt_version(
    prompt_id: str,
    payload: PromptVersionCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    prompt = _prompt_or_404(prompt_id, user.id, db)
    version_num = int(prompt.current_version) + 1
    row = PromptVersion(
        id=new_id("pmv"),
        prompt_id=prompt.id,
        version=version_num,
        template=payload.template,
        variables=payload.variables,
        metadata_json=payload.metadata,
        changelog=payload.changelog,
        created_by=user.id,
    )
    db.add(row)
    prompt.current_version = version_num
    db.add(prompt)
    db.commit()
    db.refresh(row)
    return {"version": PromptVersionOut.model_validate(row).model_dump(), "prompt_version": version_num}


@router.get("/projects/{project_id}/datasets")
def list_datasets(
    project_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    _project_or_404(project_id, user.id, db)
    rows = db.query(Dataset).filter(Dataset.project_id == project_id).order_by(Dataset.created_at.desc()).all()
    return {"data": [DatasetOut.model_validate(row).model_dump() for row in rows]}


@router.post("/projects/{project_id}/datasets", status_code=status.HTTP_201_CREATED)
def create_dataset(
    project_id: str,
    payload: DatasetCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DatasetOut:
    _project_or_404(project_id, user.id, db)
    existing = (
        db.query(Dataset)
        .filter(Dataset.project_id == project_id, Dataset.slug == payload.slug)
        .one_or_none()
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="dataset_slug_taken")
    row = Dataset(
        id=new_id("dts"),
        project_id=project_id,
        slug=payload.slug,
        description=payload.description,
        source=payload.source,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return DatasetOut.model_validate(row)


@router.post("/datasets/{dataset_id}/items", status_code=status.HTTP_201_CREATED)
def create_dataset_items(
    dataset_id: str,
    payload: DatasetItemsCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    _dataset_or_404(dataset_id, user.id, db)
    if not payload.items:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="items_required")
    current_count = db.query(DatasetItem).filter(DatasetItem.dataset_id == dataset_id).count()
    created = 0
    for idx, item in enumerate(payload.items):
        row = DatasetItem(
            id=new_id("dsi"),
            dataset_id=dataset_id,
            ord=current_count + idx,
            input=item.input,
            expected_output=item.expected_output,
            metadata_json=item.metadata,
        )
        db.add(row)
        created += 1
    db.commit()
    return {"created": created}


@router.get("/datasets/{dataset_id}/items")
def list_dataset_items(
    dataset_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    _dataset_or_404(dataset_id, user.id, db)
    rows = (
        db.query(DatasetItem)
        .filter(DatasetItem.dataset_id == dataset_id)
        .order_by(DatasetItem.ord.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {"data": [DatasetItemOut.model_validate(row).model_dump() for row in rows]}


@router.post("/datasets/{dataset_id}/build-from-traces", status_code=status.HTTP_202_ACCEPTED)
def build_dataset_from_traces(
    dataset_id: str,
    payload: DatasetBuildFromTraces,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    dataset = _dataset_or_404(dataset_id, user.id, db)
    query = db.query(Trace).filter(Trace.project_id == dataset.project_id)
    if payload.environment:
        query = query.filter(Trace.environment == payload.environment)
    if payload.status:
        query = query.filter(Trace.status == payload.status)
    if payload.name_contains:
        query = query.filter(Trace.name.ilike(f"%{payload.name_contains}%"))
    traces = query.order_by(Trace.created_at.desc()).limit(payload.limit).all()

    current_count = db.query(DatasetItem).filter(DatasetItem.dataset_id == dataset.id).count()
    created = 0
    for idx, trace in enumerate(traces):
        first_span = (
            db.query(Span)
            .filter(Span.trace_id == trace.id, Span.messages_in.isnot(None))
            .order_by(Span.started_at.asc())
            .first()
        )
        input_payload = {
            "messages": first_span.messages_in if first_span and first_span.messages_in else [],
            "trace": {
                "name": trace.name,
                "environment": trace.environment,
                "tags": trace.tags,
            },
        }
        expected_output = None
        if first_span and first_span.messages_out:
            expected_output = {"assistant_message": first_span.messages_out}
        row = DatasetItem(
            id=new_id("dsi"),
            dataset_id=dataset.id,
            ord=current_count + idx,
            input=input_payload,
            expected_output=expected_output,
            metadata_json={"source_trace_id": trace.id, "source": "traces"},
        )
        db.add(row)
        created += 1
    db.commit()
    return {"created": created, "dataset_id": dataset.id}


@router.get("/projects/{project_id}/experiments")
def list_experiments(
    project_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    _project_or_404(project_id, user.id, db)
    rows = db.query(Experiment).filter(Experiment.project_id == project_id).order_by(Experiment.created_at.desc()).all()
    return {"data": [ExperimentOut.model_validate(row).model_dump() for row in rows]}


@router.post("/projects/{project_id}/experiments", status_code=status.HTTP_201_CREATED)
def create_experiment(
    project_id: str,
    payload: ExperimentCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ExperimentOut:
    _project_or_404(project_id, user.id, db)
    dataset = _dataset_or_404(payload.dataset_id, user.id, db)
    rubric = db.get(Rubric, payload.rubric_id)
    if not rubric or rubric.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    if dataset.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    variants_dump = [variant.model_dump() for variant in payload.variants]
    try:
        validate_variants(variants_dump, payload.baseline_variant)
    except ExperimentValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )
    row = Experiment(
        id=new_id("exp"),
        project_id=project_id,
        name=payload.name,
        dataset_id=payload.dataset_id,
        rubric_id=payload.rubric_id,
        variants=variants_dump,
        pass_criteria=payload.pass_criteria,
        baseline_variant=payload.baseline_variant,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return ExperimentOut.model_validate(row)


@router.post("/experiments/{experiment_id}/run", status_code=status.HTTP_202_ACCEPTED)
def run_experiment(
    experiment_id: str,
    payload: ExperimentRunRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    experiment = _experiment_or_404(experiment_id, user.id, db)
    run = ExperimentRun(
        id=new_id("exr"),
        experiment_id=experiment.id,
        project_id=experiment.project_id,
        status="running",
        triggered_by=payload.triggered_by,
        started_at=utcnow(),
        by_variant={},
        comparisons={},
        criteria_failures=[],
        run_metadata={},
    )
    db.add(run)
    db.flush()
    try:
        result = execute_experiment(experiment, db)
        run.status = "completed"
        run.passed = bool(result["passed"])
        run.by_variant = result["by_variant"]
        run.comparisons = result["comparisons"]
        run.criteria_failures = result["criteria_failures"]
        run.run_metadata = result["run_metadata"]
    except (ValueError, ExperimentValidationError) as exc:
        run.status = "error"
        run.passed = False
        run.run_metadata = {"error": str(exc)}
    run.completed_at = utcnow()
    db.add(run)
    db.commit()
    db.refresh(run)
    return {"run_id": run.id, "status": run.status, "passed": run.passed}


@router.get("/experiments/{experiment_id}/runs/{run_id}")
def get_experiment_run(
    experiment_id: str,
    run_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    experiment = _experiment_or_404(experiment_id, user.id, db)
    run = db.get(ExperimentRun, run_id)
    if not run or run.experiment_id != experiment.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    return {"run": ExperimentRunOut.model_validate(run).model_dump()}
