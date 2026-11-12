"""F0 contracts and SPEC-003 arithmetic fixture without provider calls."""
import json
import math

import pytest
from pydantic import ValidationError

from app.domain.tasks.access import AccessDenied, Source, authorize_sources, derive_label
from app.domain.tasks.contracts import AccessLabel, MetricFact, PredictionRow, SnapshotContent
from app.domain.tasks.regression import evaluate


def snapshot(values=(1, 2, 3), segments=()):
    return SnapshotContent(task_schema={"target": {"name": "price", "unit": "BRL"}, "segments": segments}, items=[
        {"sample_id": f"s{i}", "input": {"x": i}, "expected_output": {"value": value}}
        for i, value in enumerate(values)
    ])


def rows(values=(1, 2, 5)):
    return tuple(PredictionRow(sample_id=f"s{i}", prediction={"value": value}) for i, value in enumerate(values))


def test_sealed_fixture_roundtrip():
    facts = evaluate(snapshot(), rows())
    for fact, expected in zip(facts, (2/3, 4/3, math.sqrt(4/3), -1)):
        assert fact.value == pytest.approx(expected, abs=1e-12)
        assert fact.n_total == fact.n_valid == 3 and fact.coverage == 1
        assert MetricFact.model_validate_json(fact.model_dump_json()) == fact
    assert facts[2].value > 1
    assert facts[3].statistics["sst"].value == 2
    assert facts[3].aggregation.normalization_count is None
    assert [p.y for p in facts[-1].value.points] == [0, 0, 2]


def test_canonical_and_materialized_snapshot():
    original = snapshot()
    materialized = original.materialize()
    reversed_items = original.model_copy(update={"items": tuple(reversed(original.items))})
    assert original.content_hash == reversed_items.content_hash
    assert evaluate(original, rows()) == evaluate(reversed_items, tuple(reversed(rows())))
    original.items[0].input["x"] = 999
    assert json.loads(materialized)["items"][0]["input"]["x"] == 0
    assert original.content_hash != SnapshotContent.model_validate_json(materialized).content_hash


@pytest.mark.parametrize("value", [True, "2", float("nan"), float("inf"), -float("inf")])
def test_reject_invalid_targets(value):
    with pytest.raises(ValidationError):
        snapshot((value,))


def test_nested_nonfinite():
    data = snapshot().model_dump()
    data["items"][0]["input"]["nested"] = {"value": float("nan")}
    with pytest.raises(ValidationError):
        SnapshotContent.model_validate(data)


def test_missing_constant_single_overflow():
    assert all(f.state == "missing" and f.value is None for f in evaluate(snapshot((None, None, None)), rows()))
    assert evaluate(snapshot((1, None, 3)), rows())[0].coverage == 2/3
    constant = evaluate(snapshot((2, 2, 2)), rows())[3]
    assert constant.reason == "constant_target" and constant.coverage == 1
    assert constant.statistics["sst"].value == 0
    assert evaluate(snapshot((1,)), rows((2,)))[3].reason == "insufficient_samples"
    overflow = evaluate(snapshot((1e308,)), rows((-1e308,)))
    assert all(f.state == "error" and f.reason == "numeric_overflow" for f in overflow)
    json.dumps([f.model_dump(mode="json") for f in overflow], allow_nan=False)


def test_prediction_ids_and_errors():
    with pytest.raises(ValueError, match="duplicate_sample_id"):
        evaluate(snapshot(), rows() + rows()[:1])
    with pytest.raises(ValueError, match="unknown_sample_id"):
        evaluate(snapshot((1,)), rows())
    assert evaluate(snapshot(), (PredictionRow(sample_id="s0", error="failed"),))[0].coverage == 0


def test_segments():
    data = snapshot(segments=("region",)).model_dump()
    data["items"][0]["metadata"]["region"] = "north"
    facts = evaluate(SnapshotContent.model_validate(data), rows())
    grouped = [f for f in facts if f.scope == "group" and f.definition_id == "regression.mae"]
    assert len(grouped) == 2 and sum(f.n_total for f in grouped) == 3
    assert any("__missing__" in f.scope_key for f in grouped)


@pytest.mark.parametrize("patch", [
    {"value": True}, {"value": None}, {"coverage": 0.5}, {"n_valid": 4}, {"n_total": True},
    {"definition_version": "2"}, {"direction": "maximize"},
    {"aggregation": {"method": "mean", "normalization_count": 2}},
])
def test_metric_adversaries(patch):
    fact = evaluate(snapshot(), rows())[0].model_dump()
    with pytest.raises(ValidationError):
        MetricFact.model_validate({**fact, **patch})


def label(allowed=("dev",), refs=()):
    return AccessLabel(origin_environments=("dev",), allowed_environments=allowed, source_refs=refs)


def test_current_sources_environment_project_and_cycle():
    sources = {"root": Source("p", label())}
    derived = Source("p", label(refs=("root",)), "dev")
    def check(value):
        authorize_sources(value, project_id="p", environment="dev", resolve=sources.__getitem__)
    check(derived)
    sources["root"] = Source("p", label(("prod",)))
    for forbidden in (derived, Source("other", label()), Source("p", None), Source("p", label(), "prod")):
        with pytest.raises(AccessDenied):
            check(forbidden)
    sources["root"] = Source("p", label(refs=("root",)))
    with pytest.raises(AccessDenied):
        check(derived)
    with pytest.raises(AccessDenied):
        derive_label((Source("p", label()), Source("p", label(("prod",)))), project_id="p",
                     environment="dev", resolve=sources.__getitem__, source_refs=("a", "b"))


def test_shared_result_has_no_invented_pass_fail_and_stable_hashes():
    from app.domain.tasks.contracts import TaskResult
    from app.domain.tasks.regression import evaluate_task
    first = evaluate_task(snapshot(), rows())
    second = evaluate_task(snapshot(), tuple(reversed(rows())))
    assert first == second
    assert first.decision == "inconclusive"
    assert first.decision_reasons == ("no_quality_policy",)
    assert "passed" not in first.model_dump()
    assert TaskResult.model_validate_json(first.model_dump_json()) == first


def test_version_config_and_duplicate_snapshot_validation():
    from app.domain.tasks.contracts import EvaluatorManifest, ModelVersionContent
    model = ModelVersionContent(name="linear", version_ref="commit-1")
    assert model.provenance == "partial"
    assert model.content_hash != ModelVersionContent(name="linear", version_ref="commit-2").content_hash
    with pytest.raises(ValidationError):
        EvaluatorManifest(config={"silently_ignored": True})
    data = snapshot().model_dump()
    data["items"] = [data["items"][0], data["items"][0]]
    with pytest.raises(ValidationError):
        SnapshotContent.model_validate(data)


def test_partial_residuals_preserve_gap():
    series = evaluate(snapshot((1, None, 3)), rows())[-1]
    assert series.state == "measured" and series.coverage == 2/3
    assert len(series.value.points) == 3
    assert series.value.points[1].y is None
    assert series.value.points[1].reason == "missing_reference"


def test_missing_transitive_source_denies_access():
    with pytest.raises(AccessDenied):
        authorize_sources(Source("p", label(refs=("deleted",))), project_id="p", environment="dev", resolve={ }.__getitem__)


def test_large_json_integer_reports_overflow_without_crash():
    with pytest.raises(ValidationError):
        snapshot((10**400,))


def test_typed_matrix_roundtrip_and_adversaries():
    data = {"definition_id": "classification.confusion", "value_type": "matrix", "unit": "count", "direction": "none",
        "state": "measured", "reason": None, "n_total": 3, "n_valid": 3, "coverage": 1,
        "aggregation": {"method": "count", "normalization_count": None},
        "value": {"row_axis": {"name": "actual", "labels": ["no", "yes"]},
                  "column_axis": {"name": "predicted", "labels": ["no", "yes"]}, "cells": [[1,1],[0,1]]}}
    fact = MetricFact.model_validate(data)
    assert MetricFact.model_validate_json(fact.model_dump_json()) == fact
    for cells in ([[1],[2]], [[-1,2],[1,1]], [[True,1],[0,1]], [[1,"NaN"],[0,1]], [[0,0],[0,0]]):
        with pytest.raises(ValidationError):
            MetricFact.model_validate({**data, "value": {**data["value"], "cells": cells}})


def test_group_keys_are_bounded_before_postgres_index_writes():
    data = snapshot(segments=("region",)).model_dump()
    data["items"][0]["metadata"]["region"] = "x" * 3000
    with pytest.raises(ValidationError, match="segment_group_key_too_large"):
        SnapshotContent.model_validate(data)
