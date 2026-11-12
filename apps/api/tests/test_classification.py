"""Manual classification fixtures: missing classes/probabilities never become zero metrics."""
import math

import pytest
from pydantic import ValidationError

from app.domain.tasks.contracts import ClassificationManifest, PredictionRow, SnapshotContent
from app.domain.tasks.classification import evaluate_task


def fixture(labels=("no", "yes"), actual=("no", "no", "yes", "yes"), predicted=("no", "yes", "yes", "no"), scores=(.1, .4, .35, .8)):
    schema = {"task_type": "classification", "label_set": labels, "positive_label": "yes" if len(labels) == 2 else None}
    snapshot = SnapshotContent(task_schema=schema, items=[{"sample_id": str(i), "input": {}, "expected_output": {"label": label}} for i, label in enumerate(actual)])
    rows = tuple(PredictionRow(sample_id=str(i), prediction={"label": label, **({"class_order": labels, "probabilities": [1-scores[i], scores[i]]} if scores is not None else {})}) for i, label in enumerate(predicted))
    return snapshot, rows


def facts(snapshot, rows):
    result = evaluate_task(snapshot, rows, ClassificationManifest())
    assert result.decision == "inconclusive" and result.decision_reasons == ("no_quality_policy",)
    return result, {(fact.definition_id, fact.averaging, fact.class_label): fact for fact in result.metrics}


def test_binary_manual_fixture_and_order_independence():
    snapshot, rows = fixture()
    result, values = facts(snapshot, rows)
    def value(name, average=None, label=None):
        return values[("classification." + name, average, label)].value
    assert value("accuracy") == .5
    assert value("confusion").cells == ((1, 1), (1, 1))
    for kind in ("precision", "recall", "f1"):
        assert value(kind, "macro") == .5 and value(kind, "micro") == .5 and value(kind, "weighted") == .5
    assert value("support", "class", "yes") == 2
    assert value("roc_auc", "binary", "yes") == .75
    assert math.isclose(value("average_precision", "binary", "yes"), 5/6, abs_tol=1e-12)
    assert math.isclose(value("brier"), .158125, abs_tol=1e-12)
    assert math.isclose(value("ece"), .3375, abs_tol=1e-12)
    reliability = values[("classification.reliability", None, None)]
    assert sum(stat.value for stat in reliability.statistics.values()) == 4
    assert len(reliability.value.points) == 10
    reordered = SnapshotContent(task_schema=snapshot.task_schema, items=tuple(reversed(snapshot.items)))
    assert evaluate_task(reordered, tuple(reversed(rows)), ClassificationManifest()) == result


def test_missing_probabilities_absent_class_and_score_ties():
    snapshot, rows = fixture(actual=("no",) * 4, predicted=("no",) * 4, scores=None)
    _, values = facts(snapshot, rows)
    assert values[("classification.accuracy", None, None)].value == 1
    assert values[("classification.recall", "class", "yes")].state == "not_applicable"
    assert values[("classification.f1", "macro", None)].value is None
    assert values[("classification.f1", "weighted", None)].value == 1
    assert values[("classification.roc_auc", "binary", "yes")].reason == "missing_probabilities"
    assert values[("classification.roc_auc", "binary", "yes")].coverage == 0
    snapshot, rows = fixture(scores=(.5,) * 4)
    _, values = facts(snapshot, rows)
    assert values[("classification.roc_auc", "binary", "yes")].value == .5
    assert values[("classification.average_precision", "binary", "yes")].value == .5


def test_multiclass_absent_labels_keep_macro_undefined():
    snapshot, rows = fixture(labels=("no", "yes", "other"), scores=None)
    _, values = facts(snapshot, rows)
    assert values[("classification.confusion", None, None)].value.cells == ((1, 1, 0), (1, 1, 0), (0, 0, 0))
    assert values[("classification.f1", "macro", None)].reason == "undefined_class_metric"
    assert values[("classification.brier", None, None)].value is None


@pytest.mark.parametrize("prediction", [
    {"label": "unknown"},
    {"label": "yes", "probabilities": [.1, .9], "class_order": ["yes", "no"]},
    {"label": "yes", "probabilities": [.1, .8], "class_order": ["no", "yes"]},
    {"label": "yes", "probabilities": [float("nan"), .9], "class_order": ["no", "yes"]},
    {"value": 1},
])
def test_reject_invalid_class_predictions(prediction):
    snapshot, _ = fixture()
    with pytest.raises((ValueError, ValidationError)):
        evaluate_task(snapshot, (PredictionRow(sample_id="0", prediction=prediction),), ClassificationManifest())


def test_empty_labels_and_missing_rows_report_coverage():
    snapshot, rows = fixture()
    result, values = facts(snapshot, rows[:2])
    assert result.n_valid == 2 and result.coverage == .5
    assert values[("classification.roc_auc", "binary", "yes")].reason == "both_classes_required"
    empty = SnapshotContent(task_schema=snapshot.task_schema, items=[])
    result, values = facts(empty, ())
    assert result.coverage is None and values[("classification.accuracy", None, None)].value is None


def test_multiclass_ovr_and_rejected_reference():
    schema = {"task_type": "classification", "label_set": ["a", "b", "c"]}
    snapshot = SnapshotContent(task_schema=schema, items=[{"sample_id": label, "input": {}, "expected_output": {"label": label}} for label in ("a", "b", "c")])
    rows = tuple(PredictionRow(sample_id=label, prediction={"label": label, "class_order": ["a", "b", "c"], "probabilities": [.8 if name == label else .1 for name in ("a", "b", "c")]}) for label in ("a", "b", "c"))
    _, values = facts(snapshot, rows)
    assert values[("classification.roc_auc", "ovr_macro", None)].value == 1
    assert values[("classification.average_precision", "ovr_weighted", None)].value == 1
    assert values[("classification.reliability", None, None)].reason == "binary_only"
    rejected = SnapshotContent(task_schema=schema, items=[{**item.model_dump(mode="json"), "reference_status": "rejected" if item.sample_id == "a" else "draft"} for item in snapshot.items])
    result, values = facts(rejected, rows)
    assert result.n_valid == 2
    assert values[("classification.roc_auc", "ovr_macro", None)].value is None
    assert next(point for point in values[("classification.correctness", None, None)].value.points if point.key == "a").reason == "rejected_reference"


def test_binary_requires_explicit_positive_and_never_accepts_scalar_reference():
    for schema, reference in [
        ({"task_type": "classification", "label_set": ["no", "yes"]}, {"label": "yes"}),
        ({"task_type": "classification", "label_set": ["no", "yes"], "positive_label": "yes"}, {"value": 1}),
    ]:
        with pytest.raises(ValidationError):
            SnapshotContent(task_schema=schema, items=[{"sample_id": "s", "input": {}, "expected_output": reference}])
