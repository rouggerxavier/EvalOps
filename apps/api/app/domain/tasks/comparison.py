"""Descriptive paired comparisons; policy is persisted and never implies statistical significance."""
import math

from fastapi import HTTPException

from app import models as m
from app.domain.tasks import service as s
from app.domain.tasks.contracts import SnapshotContent, PredictionRow, digest
from app.domain.tasks.regression import evaluate
from app.security import new_id


def experiment(db, actor, identifier, permission="read"):
    row = db.get(m.Experiment, identifier)
    if not row:
        raise HTTPException(404, "not_found")
    s.project_access(db, actor, row.project_id, permission)
    if row.kind == "task_comparison":
        s.load(db, actor, "snapshot", row.snapshot_id, project_id=row.project_id)
    elif actor.principal_id:
        raise HTTPException(404, "not_found")
    return row


def create_experiment(db, actor, project_id, payload):
    s.project_access(db, actor, project_id, "write")
    snap = s.load(db, actor, "snapshot", payload.snapshot_id, project_id=project_id, environment=payload.environment)
    if snap.dataset_id != payload.dataset_id:
        raise HTTPException(404, "not_found")
    if (len({variant.name for variant in payload.variants}) != len(payload.variants)
            or len({variant.model_version_id for variant in payload.variants}) != len(payload.variants)):
        raise HTTPException(422, "duplicate_variant")
    for variant in payload.variants:
        s.load(db, actor, "model", variant.model_version_id, project_id=project_id, environment=payload.environment)
    row = m.Experiment(id=new_id("exp"), project_id=project_id, name=payload.name, kind="task_comparison",
                       dataset_id=snap.dataset_id, snapshot_id=snap.id, rubric_id=None,
                       variants=[variant.model_dump() for variant in payload.variants], pass_criteria={"environment": payload.environment, "access_label": s.derived_label(db, [f"snapshot:{snap.id}"] + [f"model:{variant.model_version_id}" for variant in payload.variants], project_id, payload.environment)})
    db.add(row)
    return "experiment", row


def prediction_map(db, evaluation):
    return {row.sample_id: PredictionRow.model_validate(row.content)
            for row in db.query(m.Prediction).filter_by(set_id=evaluation.prediction_set_id).all()}


def validate_rules(policy, snapshot):
    ids = set(policy.critical_case_ids)
    samples = {item.sample_id for item in snapshot.items}
    if len(ids) != len(policy.critical_case_ids) or ids - samples or len(policy.critical_rules) != len(ids):
        raise HTTPException(422, "invalid_critical_rules")
    rules = {}
    for rule in policy.critical_rules:
        if (set(rule) != {"sample_id", "evaluator_id", "evaluator_version", "config"}
                or rule["sample_id"] not in ids or rule["sample_id"] in rules
                or rule["evaluator_id"] != "regression.case_tolerance" or rule["evaluator_version"] != "1"):
            raise HTTPException(422, "invalid_critical_rules")
        config = rule["config"]
        if not isinstance(config, dict) or set(config) - {"unit", "max_absolute_error", "max_relative_error", "relative_epsilon"}:
            raise HTTPException(422, "invalid_critical_rules")
        if config.get("unit") != snapshot.task_schema.target.unit or not any(key in config for key in ("max_absolute_error", "max_relative_error")):
            raise HTTPException(422, "invalid_critical_rules")
        for key in ("max_absolute_error", "max_relative_error", "relative_epsilon"):
            if key in config and (type(config[key]) not in (int,float) or not math.isfinite(config[key]) or config[key] < 0):
                raise HTTPException(422, "invalid_critical_rules")
        if "max_relative_error" in config and config.get("relative_epsilon", 0) <= 0:
            raise HTTPException(422, "invalid_critical_rules")
        rules[rule["sample_id"]] = rule
    return rules


def critical_result(item, prediction, rule):
    config = rule["config"]
    result = {"sample_id": item.sample_id, "rule_id": rule["evaluator_id"], "rule_version": "1",
              "config_hash": digest(config), "reference_ref": item.sample_id,
              "state": "missing", "absolute_error": None, "relative_error": None,
              "decision": "inconclusive", "reason": "invalid_reference"}
    # Reviewed status alone is insufficient: the snapshot must retain human review provenance.
    review = item.metadata.get("reference_review", {})
    if item.reference_status != "reviewed" or not review.get("actor_user_id") or not review.get("reason"):
        result["state"] = "not_applicable"
        return result
    if item.expected_output is None or item.expected_output.value is None:
        return result
    if prediction is None or prediction.error or prediction.prediction is None or prediction.prediction.value is None:
        result["reason"] = "missing_prediction"
        return result
    try:
        absolute = abs(prediction.prediction.value - item.expected_output.value)
        relative = absolute / max(abs(item.expected_output.value), config["relative_epsilon"]) if "max_relative_error" in config else None
        if not math.isfinite(absolute) or (relative is not None and not math.isfinite(relative)):
            raise ValueError("numeric_overflow")
    except (ValueError, OverflowError):
        result.update(state="error", reason="evaluator_error")
        return result
    failed = ("max_absolute_error" in config and absolute > config["max_absolute_error"]) or (relative is not None and relative > config["max_relative_error"])
    result.update(state="measured", absolute_error=absolute, relative_error=relative,
                  decision="fail" if failed else "pass", reason="tolerance_exceeded" if failed else None)
    return result


def create_comparison(db, actor, row, payload):
    s.project_access(db, actor, row.project_id, "evaluate")
    if row.kind != "task_comparison":
        raise HTTPException(422, "incompatible_evaluation_kind")
    policy = payload.policy
    policy_hash = digest(policy.model_dump(mode="json"))
    if len(set(payload.candidate_evaluation_ids)) != len(payload.candidate_evaluation_ids) or payload.baseline_evaluation_id in payload.candidate_evaluation_ids:
        raise HTTPException(422, "duplicate_evaluation")
    baseline = s.load(db, actor, "evaluation", payload.baseline_evaluation_id, project_id=row.project_id)
    candidates = [s.load(db, actor, "evaluation", identifier, project_id=row.project_id) for identifier in payload.candidate_evaluation_ids]
    environment = row.pass_criteria["environment"]
    snap = s.load(db, actor, "snapshot", row.snapshot_id, project_id=row.project_id, environment=environment)
    snapshot = SnapshotContent.model_validate_json(snap.content)
    rules = validate_rules(policy, snapshot)
    refs = [f"evaluation:{value.id}" for value in [baseline, *candidates]]
    label = s.derived_label(db, refs, row.project_id, environment)
    base_rows = prediction_map(db, baseline)
    base_set = db.get(m.PredictionSet, baseline.prediction_set_id)
    variant_models = {variant["model_version_id"]: variant["name"] for variant in row.variants}
    if len(variant_models) != len(row.variants):
        raise HTTPException(422, "duplicate_variant_model")
    outputs = []
    metric_id = policy.primary_metric.split("@")[0]
    for candidate in candidates:
        candidate_rows = prediction_map(db, candidate)
        prediction_set = db.get(m.PredictionSet, candidate.prediction_set_id)
        if base_set.model_version_id not in variant_models or prediction_set.model_version_id not in variant_models:
            raise HTTPException(422, "evaluation_not_in_variants")
        incompatible = (base_set.snapshot_id != snap.id or prediction_set.snapshot_id != snap.id
                        or baseline.environment != environment or candidate.environment != environment
                        or baseline.status != "succeeded" or candidate.status != "succeeded"
                        or not baseline.result.get("config_hash") or not candidate.result.get("config_hash")
                        or baseline.result.get("config_hash") != candidate.result.get("config_hash"))
        paired_items, paired_base, paired_candidate = [], [], []
        for item in snapshot.items:
            left, right = base_rows.get(item.sample_id), candidate_rows.get(item.sample_id)
            if (item.expected_output is not None and item.expected_output.value is not None and left and right
                    and not left.error and not right.error and left.prediction and right.prediction
                    and left.prediction.value is not None and right.prediction.value is not None):
                paired_items.append(item); paired_base.append(left); paired_candidate.append(right)
        paired = SnapshotContent(task_schema=snapshot.task_schema, items=tuple(paired_items))
        base_fact = next(fact for fact in evaluate(paired, tuple(paired_base)) if fact.definition_id == metric_id and fact.scope == "dataset")
        candidate_fact = next(fact for fact in evaluate(paired, tuple(paired_candidate)) if fact.definition_id == metric_id and fact.scope == "dataset")
        valid = base_fact.state == candidate_fact.state == "measured"
        delta = candidate_fact.value - base_fact.value if valid else None
        degradation = -delta if metric_id == "regression.r2" and delta is not None else delta
        if delta is not None and not math.isfinite(delta):
            valid = False; delta = degradation = None
        n = len(paired_items); total = len(snapshot.items); coverage = n/total if total else None
        critical = [critical_result(item, candidate_rows.get(item.sample_id), rules[item.sample_id]) for item in snapshot.items if item.sample_id in rules]
        reasons = []
        if incompatible: reasons.append("incompatible_protocol")
        if not valid: reasons.append("primary_metric_unavailable")
        if n < policy.min_pairs: reasons.append("insufficient_pairs")
        if coverage is None or coverage < policy.required_coverage: reasons.append("insufficient_coverage")
        if reasons:
            decision = "inconclusive"
        elif degradation > policy.max_degradation or any(result["decision"] == "fail" for result in critical):
            decision = "fail"; reasons.append("degradation_exceeded" if degradation > policy.max_degradation else "critical_case_failed")
        elif any(result["decision"] == "inconclusive" for result in critical):
            decision = "inconclusive"; reasons.append("critical_case_inconclusive")
        elif critical:
            decision = "review"; reasons.append("human_review_required")
        else:
            decision = "pass"
        outputs.append({"evaluation_id": candidate.id, "n_total": total, "n_pairs": n, "pair_coverage": coverage,
                        "baseline_value": base_fact.value if valid else None, "candidate_value": candidate_fact.value if valid else None,
                        "unit": base_fact.unit, "delta": delta, "degradation": degradation, "decision": decision,
                        "reasons": reasons, "critical_results": critical,
                        "excluded_sample_ids": sorted({item.sample_id for item in snapshot.items} - {item.sample_id for item in paired_items})})
    decision = next(value for value in ("fail", "inconclusive", "review", "pass") if any(result["decision"] == value for result in outputs))
    reasons = sorted({reason for result in outputs for reason in result["reasons"]})
    run = m.ExperimentRun(id=new_id("exr"), project_id=row.project_id, experiment_id=row.id,
                          kind="task_comparison", status="completed", passed=None, decision=decision, decision_reasons=reasons,
                          started_at=m.utcnow(), completed_at=m.utcnow(), run_metadata={
                              "schema_version": 1, "environment": environment, "snapshot_id": snap.id,
                              "policy_version": policy.policy_version, "policy_hash": policy_hash, "policy_timing": "post_observation",
                              "manifest": {**policy.model_dump(mode="json"), "baseline_evaluation_id": baseline.id},
                              "n_total": len(snapshot.items), "n_pairs": min(result["n_pairs"] for result in outputs),
                              "pair_coverage": min((result["pair_coverage"] for result in outputs if result["pair_coverage"] is not None), default=None),
                              "candidates": outputs, "access_label": label})
    db.add(run); db.flush()
    for evaluation in [baseline, *candidates]:
        version = db.get(m.PredictionSet, evaluation.prediction_set_id).model_version_id
        db.add(m.ExperimentRunEvaluation(project_id=row.project_id, run_id=run.id, variant_name=variant_models[version], task_evaluation_id=evaluation.id))
    return "comparison", run
