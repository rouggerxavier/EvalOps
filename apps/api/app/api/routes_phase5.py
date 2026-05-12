from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import ensure_org_membership, get_current_user
from app.domain.evaluators.base import EvaluatorResult
from app.domain.evaluators.registry import REGISTRY
from app.domain.rubrics.resolver import build_trace_context
from app.domain.services.eval_service import _aggregate
from app.models import (
    Dataset,
    DatasetItem,
    EvaluatorRow,
    Experiment,
    ExperimentRun,
    Project,
    Prompt,
    PromptVersion,
    Rubric,
    RubricVersion,
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


def _trace_context_from_item(item: DatasetItem, db: Session) -> dict:
    metadata = item.metadata_json or {}
    source_trace_id = metadata.get("source_trace_id")
    if isinstance(source_trace_id, str):
        trace = db.get(Trace, source_trace_id)
        if trace:
            spans = db.query(Span).filter(Span.trace_id == trace.id).all()
            return build_trace_context(trace, spans)
    return {
        "trace": {
            "input": item.input or {},
            "output": item.expected_output or {},
            "metadata": metadata,
        }
    }


def _run_rubric_on_context(rubric_version: RubricVersion, context: dict, db: Session) -> dict:
    parsed_spec = rubric_version.parsed_spec or {}
    aggregate_method = parsed_spec.get("aggregate", "weighted_mean")
    threshold = float(parsed_spec.get("threshold", 0.7))
    fail_fast_global = bool(parsed_spec.get("fail_fast", False))
    auto_fail_conditions = parsed_spec.get("automatic_fail_conditions", [])

    evaluator_rows = (
        db.query(EvaluatorRow)
        .filter(
            EvaluatorRow.rubric_version_id == rubric_version.id,
            EvaluatorRow.enabled == True,  # noqa: E712
        )
        .order_by(EvaluatorRow.ord)
        .all()
    )

    score_rows: list[tuple[str, float, bool, float, int]] = []
    for row in evaluator_rows:
        run_fn = REGISTRY.get(row.type)
        if run_fn is None:
            result = EvaluatorResult(score=0.0, passed=False, reasoning=f"unknown evaluator: {row.type}")
        else:
            try:
                result = run_fn(context, row.config)
            except Exception as exc:  # noqa: BLE001
                result = EvaluatorResult(score=0.0, passed=False, reasoning=f"Evaluator error: {exc}")
        score_rows.append((row.slug, float(result.score), bool(result.passed), float(result.cost_usd), int(result.latency_ms)))
        if (row.fail_fast or fail_fast_global) and not result.passed:
            break

    weight_map = {row.slug: float(row.weight) for row in evaluator_rows}
    aggregate_pairs = [(score, weight_map.get(slug, 1.0)) for slug, score, _, _, _ in score_rows]
    aggregate_score = float(_aggregate(aggregate_pairs, aggregate_method))

    score_by_slug = {slug: passed for slug, _, passed, _, _ in score_rows}
    auto_failed = False
    for cond in auto_fail_conditions:
        ev_id = cond.get("evaluator_id")
        if isinstance(ev_id, str) and ev_id in score_by_slug and not score_by_slug[ev_id]:
            auto_failed = True
            break

    total_cost = sum(cost for _, _, _, cost, _ in score_rows)
    total_latency = sum(lat for _, _, _, _, lat in score_rows)
    return {
        "score": aggregate_score,
        "passed": aggregate_score >= threshold and not auto_failed,
        "cost_usd": total_cost,
        "latency_ms": total_latency,
        "evaluators": [
            {"slug": slug, "score": score, "passed": passed, "cost_usd": cost, "latency_ms": latency}
            for slug, score, passed, cost, latency in score_rows
        ],
    }


def _execute_experiment(experiment: Experiment, db: Session) -> dict:
    dataset = db.get(Dataset, experiment.dataset_id)
    rubric = db.get(Rubric, experiment.rubric_id)
    if not dataset or not rubric:
        raise ValueError("dataset_or_rubric_not_found")

    rubric_version = (
        db.query(RubricVersion)
        .filter(RubricVersion.rubric_id == rubric.id, RubricVersion.version == rubric.current_version)
        .one_or_none()
    )
    if rubric_version is None:
        raise ValueError("rubric_version_not_found")

    items = db.query(DatasetItem).filter(DatasetItem.dataset_id == dataset.id).order_by(DatasetItem.ord.asc()).all()
    if not items:
        raise ValueError("dataset_has_no_items")

    variants = experiment.variants or []
    if not variants:
        raise ValueError("experiment_has_no_variants")

    by_variant: dict[str, dict] = {}
    item_results: dict[str, list] = {}
    for variant in variants:
        name = str(variant.get("name", "")).strip()
        if not name:
            raise ValueError("variant_name_required")
        scores: list[float] = []
        costs: list[float] = []
        latencies: list[int] = []
        passes = 0
        variant_item_results: list[dict] = []
        for item in items:
            context = _trace_context_from_item(item, db)
            result = _run_rubric_on_context(rubric_version, context, db)
            scores.append(float(result["score"]))
            costs.append(float(result["cost_usd"]))
            latencies.append(int(result["latency_ms"]))
            if result["passed"]:
                passes += 1
            variant_item_results.append(
                {
                    "dataset_item_id": item.id,
                    "passed": bool(result["passed"]),
                    "score": float(result["score"]),
                }
            )
        total_items = len(items)
        by_variant[name] = {
            "pass_rate": round(passes / total_items, 6),
            "avg_score": round(sum(scores) / total_items, 6),
            "avg_latency_ms": int(sum(latencies) / total_items),
            "total_cost_usd": round(sum(costs), 6),
            "avg_cost_usd_per_item": round(sum(costs) / total_items, 6),
            "total_items": total_items,
        }
        item_results[name] = variant_item_results

    baseline_name = experiment.baseline_variant or str(variants[0].get("name"))
    if baseline_name not in by_variant:
        baseline_name = str(variants[0].get("name"))
    baseline = by_variant[baseline_name]

    comparisons: dict[str, dict] = {}
    criteria = experiment.pass_criteria or {}
    no_regression_delta = float(criteria.get("no_regression_delta", 0.02))
    for name, metrics in by_variant.items():
        if name == baseline_name:
            continue
        delta_pass = metrics["pass_rate"] - baseline["pass_rate"]
        delta_cost = metrics["total_cost_usd"] - baseline["total_cost_usd"]
        comparisons[f"{name}_vs_{baseline_name}"] = {
            "delta_pass_rate": round(delta_pass, 6),
            "delta_cost": round(delta_cost, 6),
            "regression": delta_pass < -no_regression_delta,
        }

    criteria_failures: list[str] = []
    min_pass_rate = criteria.get("min_pass_rate")
    if min_pass_rate is not None:
        threshold = float(min_pass_rate)
        for name, metrics in by_variant.items():
            if float(metrics["pass_rate"]) < threshold:
                criteria_failures.append(f"{name}.pass_rate<{threshold}")

    max_avg_cost = criteria.get("max_avg_cost_usd_per_item")
    if max_avg_cost is not None:
        limit = float(max_avg_cost)
        for name, metrics in by_variant.items():
            if float(metrics["avg_cost_usd_per_item"]) > limit:
                criteria_failures.append(f"{name}.avg_cost_usd_per_item>{limit}")

    no_regression_vs = str(criteria.get("no_regression_vs", baseline_name))
    if no_regression_vs in by_variant:
        base_metrics = by_variant[no_regression_vs]
        base_rate = float(base_metrics["pass_rate"])
        for name, metrics in by_variant.items():
            if name == no_regression_vs:
                continue
            if float(metrics["pass_rate"]) < base_rate - no_regression_delta:
                criteria_failures.append(f"{name}.pass_rate<{no_regression_vs}-delta")

    passed = len(criteria_failures) == 0
    return {
        "passed": passed,
        "by_variant": by_variant,
        "comparisons": comparisons,
        "criteria_failures": criteria_failures,
        "run_metadata": {
            "dataset_id": dataset.id,
            "rubric_id": rubric.id,
            "rubric_version": rubric.current_version,
            "baseline_variant": baseline_name,
            "item_results": item_results,
        },
    }


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
    row = Experiment(
        id=new_id("exp"),
        project_id=project_id,
        name=payload.name,
        dataset_id=payload.dataset_id,
        rubric_id=payload.rubric_id,
        variants=[variant.model_dump() for variant in payload.variants],
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
        result = _execute_experiment(experiment, db)
        run.status = "completed"
        run.passed = bool(result["passed"])
        run.by_variant = result["by_variant"]
        run.comparisons = result["comparisons"]
        run.criteria_failures = result["criteria_failures"]
        run.run_metadata = result["run_metadata"]
    except ValueError as exc:
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
