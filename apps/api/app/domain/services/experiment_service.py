"""Experiment execution — variants influence output deterministically.

Phase 3 (G-05): each ExperimentVariant resolves to a prompt template + model
config and produces its own synthesized assistant output per dataset item.
The rubric is evaluated against that variant-specific output, so A/B
comparisons reflect real differences between variant configs.

Synchronous, no LLM, no worker. Suitable for MVP.
"""
from __future__ import annotations

import json
from typing import Any

from jinja2 import Environment
from sqlalchemy.orm import Session

from app.domain.evaluators.base import EvaluatorResult
from app.domain.evaluators.registry import REGISTRY
from app.domain.rubrics.resolver import build_trace_context
from app.domain.services.eval_service import _aggregate
from app.models import (
    Dataset,
    DatasetItem,
    EvaluatorRow,
    Experiment,
    Prompt,
    PromptVersion,
    Rubric,
    RubricVersion,
    Span,
    Trace,
)

_jinja = Environment(autoescape=False)


class ExperimentValidationError(Exception):
    """Invalid experiment configuration (maps to HTTP 422 in routes)."""


def validate_variants(variants: list[dict] | list[Any], baseline_variant: str | None) -> None:
    if not variants:
        raise ExperimentValidationError("variants_required")
    names: list[str] = []
    for v in variants:
        item = v if isinstance(v, dict) else (v.model_dump() if hasattr(v, "model_dump") else dict(v))
        name = str(item.get("name") or "").strip()
        if not name:
            raise ExperimentValidationError("variant_name_required")
        if name in names:
            raise ExperimentValidationError(f"variant_name_duplicate:{name}")
        names.append(name)
    if baseline_variant is not None and baseline_variant not in names:
        raise ExperimentValidationError("baseline_variant_not_in_variants")


def _extract_user_text(item_input: Any) -> str:
    if not isinstance(item_input, dict):
        return ""
    msgs = item_input.get("messages")
    if isinstance(msgs, list) and msgs:
        last = msgs[-1]
        if isinstance(last, dict):
            content = last.get("content")
            if isinstance(content, str):
                return content
    for key in ("text", "user_message", "input"):
        v = item_input.get(key)
        if isinstance(v, str):
            return v
    return ""


def _render_template(template: str, variables: dict[str, Any]) -> str:
    try:
        return _jinja.from_string(template).render(**variables)
    except Exception:  # noqa: BLE001
        return template


def _resolve_prompt_version(ref: str, project_id: str, db: Session) -> PromptVersion | None:
    pv = db.get(PromptVersion, ref)
    if pv is not None:
        prompt = db.get(Prompt, pv.prompt_id)
        if prompt and prompt.project_id == project_id:
            return pv
    if "@" in ref:
        slug, _, ver_str = ref.partition("@")
        try:
            version = int(ver_str)
        except ValueError:
            return None
        prompt = (
            db.query(Prompt)
            .filter(Prompt.project_id == project_id, Prompt.slug == slug)
            .one_or_none()
        )
        if prompt is None:
            return None
        return (
            db.query(PromptVersion)
            .filter(PromptVersion.prompt_id == prompt.id, PromptVersion.version == version)
            .one_or_none()
        )
    prompt = (
        db.query(Prompt)
        .filter(Prompt.project_id == project_id, Prompt.slug == ref)
        .one_or_none()
    )
    if prompt is None:
        return None
    return (
        db.query(PromptVersion)
        .filter(
            PromptVersion.prompt_id == prompt.id,
            PromptVersion.version == prompt.current_version,
        )
        .one_or_none()
    )


def _resolve_variant_template(variant: dict, project_id: str, db: Session) -> str:
    ref = variant.get("prompt_version_ref")
    if isinstance(ref, str) and ref.strip():
        pv = _resolve_prompt_version(ref.strip(), project_id, db)
        if pv is None:
            raise ExperimentValidationError(f"prompt_version_ref_invalid:{ref}")
        return pv.template
    return "{{ user_message }}"


def _synthesize_variant_output(template: str, variant: dict, item: DatasetItem) -> str:
    user_text = _extract_user_text(item.input)
    render_vars: dict[str, Any] = {"user_message": user_text}
    if isinstance(item.input, dict):
        for k, v in item.input.items():
            if k in render_vars:
                continue
            if isinstance(v, (str, int, float, bool)):
                render_vars[k] = v
    rendered = _render_template(template, render_vars)
    model_tag = str(variant.get("model") or "")
    params_blob = json.dumps(variant.get("params") or {}, sort_keys=True, ensure_ascii=False)
    return f"{rendered}\n[model={model_tag} params={params_blob}]"


def _build_variant_context(
    item: DatasetItem,
    variant: dict,
    assistant_text: str,
    db: Session,
) -> dict:
    user_text = _extract_user_text(item.input)
    output_block = {"assistant_message": assistant_text, "text": assistant_text}
    input_block = {"user_message": user_text, "text": user_text}

    metadata = item.metadata_json or {}
    source_trace_id = metadata.get("source_trace_id") if isinstance(metadata, dict) else None
    if isinstance(source_trace_id, str):
        trace = db.get(Trace, source_trace_id)
        if trace is not None:
            spans = db.query(Span).filter(Span.trace_id == trace.id).all()
            ctx = build_trace_context(trace, spans)
            ctx["trace"]["input"] = input_block
            ctx["trace"]["output"] = output_block
            ctx["variant"] = _variant_summary(variant)
            ctx["dataset_item"] = {"expected_output": item.expected_output or {}}
            return ctx

    return {
        "trace": {
            "input": input_block,
            "output": output_block,
            "metadata": metadata if isinstance(metadata, dict) else {},
        },
        "variant": _variant_summary(variant),
        "dataset_item": {"expected_output": item.expected_output or {}},
    }


def _variant_summary(variant: dict) -> dict:
    return {
        "name": variant.get("name"),
        "model": variant.get("model"),
        "prompt_version_ref": variant.get("prompt_version_ref"),
        "params": variant.get("params") or {},
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
        score_rows.append(
            (row.slug, float(result.score), bool(result.passed), float(result.cost_usd), int(result.latency_ms))
        )
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


def execute_experiment(experiment: Experiment, db: Session) -> dict:
    dataset = db.get(Dataset, experiment.dataset_id)
    rubric = db.get(Rubric, experiment.rubric_id)
    if dataset is None or rubric is None:
        raise ValueError("dataset_or_rubric_not_found")

    rubric_version = (
        db.query(RubricVersion)
        .filter(RubricVersion.rubric_id == rubric.id, RubricVersion.version == rubric.current_version)
        .one_or_none()
    )
    if rubric_version is None:
        raise ValueError("rubric_version_not_found")

    items = (
        db.query(DatasetItem)
        .filter(DatasetItem.dataset_id == dataset.id)
        .order_by(DatasetItem.ord.asc())
        .all()
    )
    if not items:
        raise ValueError("dataset_has_no_items")

    raw_variants = experiment.variants or []
    variants: list[dict] = []
    for v in raw_variants:
        if isinstance(v, dict):
            variants.append(v)
        elif hasattr(v, "model_dump"):
            variants.append(v.model_dump())
        else:
            variants.append(dict(v))

    validate_variants(variants, experiment.baseline_variant)

    template_by_variant: dict[str, str] = {}
    for variant in variants:
        name = str(variant["name"])
        template_by_variant[name] = _resolve_variant_template(variant, experiment.project_id, db)

    by_variant: dict[str, dict] = {}
    item_results: dict[str, list] = {}

    for variant in variants:
        name = str(variant["name"])
        template = template_by_variant[name]
        scores: list[float] = []
        costs: list[float] = []
        latencies: list[int] = []
        passes = 0
        per_item: list[dict] = []
        for item in items:
            assistant_text = _synthesize_variant_output(template, variant, item)
            context = _build_variant_context(item, variant, assistant_text, db)
            result = _run_rubric_on_context(rubric_version, context, db)
            scores.append(float(result["score"]))
            costs.append(float(result["cost_usd"]))
            latencies.append(int(result["latency_ms"]))
            if result["passed"]:
                passes += 1
            per_item.append(
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
        item_results[name] = per_item

    baseline_name = experiment.baseline_variant or str(variants[0]["name"])
    baseline = by_variant[baseline_name]

    criteria = experiment.pass_criteria or {}
    no_regression_delta = float(criteria.get("no_regression_delta", 0.02))

    comparisons: dict[str, dict] = {}
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
