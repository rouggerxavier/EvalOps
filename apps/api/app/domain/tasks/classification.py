"""classification.standard@1: closed-label offline metrics, explicit undefined states."""
import math
from itertools import groupby

from app.domain.tasks.contracts import ClassPrediction, MetricFact, Series, SnapshotContent, canonical_json


def validate_fact(fact):
    kind = fact.definition_id.removeprefix("classification.")
    series = kind in {"reliability", "correctness"}
    count = kind == "support"
    if (fact.n_valid > fact.n_total or fact.coverage != (fact.n_valid / fact.n_total if fact.n_total else None)
            or fact.value_type != ("series" if series else "scalar")
            or fact.unit != ("count" if count else "1")
            or fact.direction != ("none" if series or count else "minimize" if kind in {"brier", "ece"} else "maximize")
            or fact.aggregation.method not in {"identity", "count", "mean"}):
        raise ValueError("invalid_classification_definition")
    if fact.aggregation.normalization_count is not None:
        raise ValueError("classification_v1_identity_normalizer_required")
    if kind in {"precision", "recall", "f1"}:
        valid_average = fact.averaging in {"class", "macro", "micro", "weighted"}
    elif kind == "support":
        valid_average = fact.averaging == "class"
    elif kind in {"roc_auc", "average_precision"}:
        valid_average = fact.averaging in {"class", "binary", "ovr_macro", "ovr_weighted"}
    else:
        valid_average = fact.averaging is None
    if not valid_average or ((fact.averaging in {"class", "binary"}) != (fact.class_label is not None)):
        raise ValueError("invalid_classification_averaging")
    if kind == "reliability":
        if (set(fact.statistics) != {f"bin_{i}" for i in range(10)}
                or any(quantity.unit != "count" or type(quantity.value) is not int or quantity.value < 0 for quantity in fact.statistics.values())
                or sum(quantity.value for quantity in fact.statistics.values()) != fact.n_valid):
            # Non-binary calibration has no applicable bins.
            if fact.statistics or fact.reason != "binary_only":
                raise ValueError("invalid_calibration_bins")
    elif fact.statistics:
        raise ValueError("unexpected_classification_statistics")
    if fact.state == "measured":
        if fact.reason is not None or not fact.n_valid:
            raise ValueError("invalid_measured_classification")
        if series:
            if not isinstance(fact.value, Series) or fact.value.x_axis.unit != "1" or fact.value.y_axis.unit != "1":
                raise ValueError("invalid_reliability_series")
            if kind == "correctness" and sum(point.state == "measured" for point in fact.value.points) != fact.n_valid:
                raise ValueError("invalid_correctness_population")
            if kind == "reliability" and (len(fact.value.points) != 10 or {point.key for point in fact.value.points} != {str(i) for i in range(10)}):
                raise ValueError("invalid_reliability_bins")
            if any((kind == "reliability" and not 0 <= point.x <= 1) or point.y is not None and not 0 <= point.y <= 1 for point in fact.value.points):
                raise ValueError("invalid_probability_range")
        elif type(fact.value) not in (int, float) or not 0 <= fact.value <= (fact.n_valid if count else 1):
            raise ValueError("invalid_classification_range")
    elif fact.value is not None or not fact.reason:
        raise ValueError("invalid_unmeasured_classification")


def validate_predictions(snapshot, rows):
    schema = snapshot.task_schema
    for row in rows:
        prediction = row.prediction
        if prediction is None:
            continue
        if schema.task_type == "classification":
            if (not isinstance(prediction, ClassPrediction)
                    or prediction.label is not None and prediction.label not in schema.label_set
                    or prediction.probabilities is not None and prediction.class_order != schema.label_set):
                raise ValueError("invalid_class_prediction")
        elif isinstance(prediction, ClassPrediction):
            raise ValueError("invalid_regression_prediction")


def ranked_curves(observations):
    """Group score ties: average ROC rank and non-interpolated average precision."""
    positives = sum(actual for actual, _ in observations)
    negatives = len(observations) - positives
    if not positives or not negatives:
        return None, None
    tp = fp = 0
    roc = ap = 0.0
    for _, tied in groupby(sorted(observations, key=lambda pair: -pair[1]), key=lambda pair: pair[1]):
        group = list(tied)
        positive = sum(actual for actual, _ in group)
        negative = len(group) - positive
        roc += (tp + positive / 2) * negative / (positives * negatives)
        tp += positive
        fp += negative
        ap += positive / positives * tp / (tp + fp)
    return roc, ap


def evaluate(snapshot: SnapshotContent, rows):
    validate_predictions(snapshot, rows)
    items = {item.sample_id: item for item in snapshot.items}
    predictions = {row.sample_id: row for row in rows}
    if len(predictions) != len(rows) or predictions.keys() - items.keys():
        raise ValueError("invalid_prediction_sample_ids")
    schema = snapshot.task_schema
    labels = schema.label_set
    groups = [("dataset", "all", sorted(items))]
    for segment in schema.segments:
        grouped = {}
        for key in sorted(items):
            group_key = canonical_json({"segment": segment, "value": items[key].metadata.get(segment, "__missing__")})
            grouped.setdefault(group_key, []).append(key)
        groups.extend(("group", key, grouped[key]) for key in sorted(grouped))
    facts = []
    for scope, group_key, keys in groups:
        pairs = []
        scored = []
        for key in keys:
            item, row = items[key], predictions.get(key)
            reference = item.expected_output
            if item.reference_status == "rejected" or reference is None or reference.label is None or row is None or row.error or row.prediction is None:
                continue
            if row.prediction.label is not None:
                pairs.append((reference.label, row.prediction.label))
            if row.prediction.probabilities is not None:
                scored.append((reference.label, row.prediction.probabilities))
        n, total = len(pairs), len(keys)
        matrix = [[0 for _ in labels] for _ in labels]
        indices = {label: i for i, label in enumerate(labels)}
        for actual, predicted in pairs:
            matrix[indices[actual]][indices[predicted]] += 1
        base = dict(scope=scope, scope_key=group_key, n_total=total, n_valid=n, coverage=n / total if total else None)
        facts.append(MetricFact(**base, definition_id="classification.confusion", value_type="matrix", unit="count", direction="none",
            value={"row_axis": {"name": "actual", "labels": labels}, "column_axis": {"name": "predicted", "labels": labels}, "cells": matrix} if n else None,
            state="measured" if n else "missing", reason=None if n else "no_valid_labels", aggregation={"method": "count"}))
        def emit(kind, value, *, label=None, averaging=None, count=n, reason=None, statistics=None):
            identity = group_key if label is None and averaging is None else canonical_json({"group": group_key, "class": label, "averaging": averaging})
            facts.append(MetricFact(**{**base, "scope_key": identity, "n_valid": count, "coverage": count / total if total else None},
                definition_id=f"classification.{kind}", class_label=label, averaging=averaging,
                value_type="series" if kind in {"reliability", "correctness"} else "scalar", value=value,
                unit="count" if kind == "support" else "1", direction="none" if kind in {"support", "reliability", "correctness"} else "minimize" if kind in {"brier", "ece"} else "maximize",
                state="measured" if value is not None else "not_applicable" if reason in {"missing_probabilities", "binary_only"} or count else "missing",
                reason=None if value is not None else reason or ("no_valid_labels" if not count else "zero_denominator"),
                aggregation={"method": "identity"}, statistics=statistics or {}))
        emit("accuracy", sum(matrix[i][i] for i in range(len(labels))) / n if n else None)
        correctness = []
        for i, key in enumerate(keys):
            reference = items[key].expected_output
            row = predictions.get(key)
            reason = "rejected_reference" if items[key].reference_status == "rejected" else "missing_reference" if reference is None or reference.label is None else "missing_prediction" if row is None or row.prediction is None or row.prediction.label is None or row.error else None
            correctness.append({"key": key, "x": i, "y": int(reference.label == row.prediction.label) if reason is None else None,
                                "state": "measured" if reason is None else "missing", "reason": reason})
        emit("correctness", Series(x_axis={"name": "sample_index", "unit": "1"}, y_axis={"name": "correct", "unit": "1"}, points=correctness) if n else None)

        values = {kind: [] for kind in ("precision", "recall", "f1")}
        supports = []
        for i, label in enumerate(labels):
            tp = matrix[i][i]
            support = sum(matrix[i])
            predicted = sum(row[i] for row in matrix)
            supports.append(support)
            emit("support", support if n else None, label=label, averaging="class")
            for kind, numerator, denominator in (("precision", tp, predicted), ("recall", tp, support), ("f1", 2 * tp, support + predicted)):
                value = numerator / denominator if denominator else None
                values[kind].append(value)
                emit(kind, value, label=label, averaging="class")
        for kind, class_values in values.items():
            for average in ("macro", "weighted"):
                weights = [1] * len(labels) if average == "macro" else supports
                valid = n and all(value is not None for value, weight in zip(class_values, weights) if weight)
                value = math.fsum(value * weight for value, weight in zip(class_values, weights) if weight) / sum(weights) if valid else None
                emit(kind, value, averaging=average, reason="undefined_class_metric")
            emit(kind, sum(matrix[i][i] for i in range(len(labels))) / n if n else None, averaging="micro")
        probability_count = len(scored)
        score_labels = (schema.positive_label,) if len(labels) == 2 else labels
        auc_values = {"roc_auc": [], "average_precision": []}
        auc_support = []
        for label in score_labels:
            observations = [(actual == label, scores[indices[label]]) for actual, scores in scored]
            roc, ap = ranked_curves(observations)
            auc_support.append(sum(actual for actual, _ in observations))
            for kind, value in (("roc_auc", roc), ("average_precision", ap)):
                auc_values[kind].append(value)
                emit(kind, value, label=label, averaging="binary" if len(labels) == 2 else "class", count=probability_count,
                     reason="both_classes_required" if probability_count else "missing_probabilities")
        if len(labels) > 2:
            for kind, class_values in auc_values.items():
                for average in ("ovr_macro", "ovr_weighted"):
                    weights = [1] * len(labels) if average == "ovr_macro" else auc_support
                    value = math.fsum(value * weight for value, weight in zip(class_values, weights)) / sum(weights) if all(value is not None for value in class_values) else None
                    emit(kind, value, averaging=average, count=probability_count, reason="both_classes_required")
        if len(labels) != 2:
            for kind in ("brier", "ece", "reliability"):
                emit(kind, None, count=probability_count, reason="binary_only")
            continue
        observations = [(actual == schema.positive_label, scores[indices[schema.positive_label]]) for actual, scores in scored]
        emit("brier", math.fsum((score - actual) ** 2 for actual, score in observations) / probability_count if probability_count else None,
             count=probability_count, reason="missing_probabilities")
        bins = [[] for _ in range(10)]
        for actual, score in observations:
            bins[min(int(score * 10), 9)].append((actual, score))
        points, statistics = [], {}
        ece = 0.0
        for i, bucket in enumerate(bins):
            confidence = math.fsum(score for _, score in bucket) / len(bucket) if bucket else (i + .5) / 10
            observed = sum(actual for actual, _ in bucket) / len(bucket) if bucket else None
            if bucket:
                ece += len(bucket) / probability_count * abs(observed - confidence)
            statistics[f"bin_{i}"] = {"value": len(bucket), "unit": "count"}
            points.append({"key": str(i), "x": confidence, "y": observed, "state": "measured" if bucket else "missing", "reason": None if bucket else "empty_bin"})
        emit("ece", ece if probability_count else None, count=probability_count, reason="missing_probabilities")
        emit("reliability", Series(x_axis={"name": "mean_probability", "unit": "1"}, y_axis={"name": "positive_frequency", "unit": "1"}, points=points) if probability_count else None,
             count=probability_count, reason="missing_probabilities", statistics=statistics)
    return facts


def evaluate_task(snapshot, rows, manifest):
    from app.domain.tasks.contracts import TaskResult, digest
    facts = evaluate(snapshot, rows)
    first = facts[0]
    return TaskResult(snapshot_hash=snapshot.content_hash, prediction_hash=digest([row.model_dump(mode="json") for row in sorted(rows, key=lambda row: row.sample_id)]),
        config_hash=digest(manifest.model_dump(mode="json")), evaluator_manifest=manifest,
        n_total=first.n_total, n_valid=first.n_valid, coverage=first.coverage, metrics=tuple(facts))
