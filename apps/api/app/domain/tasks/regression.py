"""regression.standard@1: deterministic offline arithmetic, never runs a model."""
import math

from app.domain.tasks.contracts import MetricFact, PredictionRow, Series, SnapshotContent, canonical_json


def evaluate(snapshot: SnapshotContent, rows: tuple[PredictionRow, ...], *, histogram_edges=(-100, -10, -1, 0, 1, 10, 100)) -> list[MetricFact]:
    items = {item.sample_id: item for item in snapshot.items}
    predictions = {row.sample_id: row for row in rows}
    if len(predictions) != len(rows):
        raise ValueError("duplicate_sample_id")
    if predictions.keys() - items.keys():
        raise ValueError("unknown_sample_id")
    unit = snapshot.task_schema.target.unit
    groups = [("dataset", "all", tuple(sorted(items)))]
    for segment in snapshot.task_schema.segments:
        grouped: dict[str, list[str]] = {}
        for key in sorted(items):
            value = items[key].metadata.get(segment, "__missing__")
            group_key = canonical_json({"segment": segment, "value": value})
            grouped.setdefault(group_key, []).append(key)
        groups.extend(("group", key, tuple(grouped[key])) for key in sorted(grouped))
    facts = []
    for scope, scope_key, keys in groups:
        pairs = []
        for key in keys:
            reference = items[key].expected_output
            row = predictions.get(key)
            if (reference is not None and reference.value is not None and row is not None
                    and row.error is None and row.prediction is not None and row.prediction.value is not None):
                pairs.append((key, reference.value, row.prediction.value))
        n = len(pairs)
        total = len(keys)
        base = dict(scope=scope, scope_key=scope_key, n_total=total, n_valid=n,
                    coverage=n / total if total else None)
        values = {}
        statistics = {}
        overflow = False
        try:
            residuals = [predicted - expected for _, expected, predicted in pairs]
            mean = math.fsum(expected / n for _, expected, _ in pairs) if n else 0.0
            sse = math.fsum(residual * residual for residual in residuals)
            sst = math.fsum((expected - mean) ** 2 for _, expected, _ in pairs)
            values = {"mae": math.fsum(abs(r) / n for r in residuals) if n else None,
                      "mse": sse / n if n else None, "rmse": math.sqrt(sse / n) if n else None,
                      "r2": 1 - sse / sst if n >= 2 and sst else None}
            overflow = any(value is not None and not math.isfinite(value) for value in values.values())
            overflow |= not all(math.isfinite(value) for value in (sse, sst, mean, *residuals))
            if n and not overflow:
                statistics = {"sse": {"value": sse, "unit": unit + "^2"},
                              "sst": {"value": sst, "unit": unit + "^2"},
                              "target_mean": {"value": mean, "unit": unit}}
        except (OverflowError, ValueError):
            overflow = True
        for name, method in (("mae", "mean"), ("mse", "mean"), ("rmse", "root_mean"), ("r2", "r2")):
            state, reason = "measured", None
            if not n:
                state, reason = "missing", "no_valid_pairs"
            elif overflow:
                state, reason = "error", "numeric_overflow"
            elif name == "r2" and values[name] is None:
                state, reason = "not_applicable", "insufficient_samples" if n < 2 else "constant_target"
            facts.append(MetricFact(
                **base, definition_id="regression." + name, value_type="scalar",
                value=values.get(name) if state == "measured" else None,
                unit="1" if name == "r2" else unit + "^2" if name == "mse" else unit,
                direction="maximize" if name == "r2" else "minimize", state=state, reason=reason,
                aggregation={"method": method, "normalization_count": n if n and method != "r2" else None},
                statistics=statistics if name == "r2" else {},
            ))
        histogram = None
        if n and not overflow:
            from bisect import bisect_right
            counts = [0] * (len(histogram_edges) + 1)
            for value in residuals:
                counts[bisect_right(histogram_edges, value)] += 1
            labels = [f"<{histogram_edges[0]}"] + [f"[{left},{right})" for left, right in zip(histogram_edges, histogram_edges[1:])] + [f">={histogram_edges[-1]}"]
            histogram = {"row_axis": {"name": "residual_interval", "labels": labels},
                         "column_axis": {"name": "count", "labels": ["samples"]}, "cells": [[count] for count in counts]}
        facts.append(MetricFact(
            **base, definition_id="regression.residual_histogram", value_type="matrix", value=histogram, unit="count",
            direction="none", state="missing" if not n else "error" if overflow else "measured",
            reason="no_valid_pairs" if not n else "numeric_overflow" if overflow else None,
            aggregation={"method": "count", "normalization_count": None},
        ))
        series = None
        if n and not overflow:
            series = Series(x_axis={"name": "prediction", "unit": unit},
                            y_axis={"name": "residual", "unit": unit},
                            points=tuple(_residual_point(key, items[key], predictions[key])
                                         for key in keys if key in predictions
                                         and predictions[key].error is None
                                         and predictions[key].prediction is not None
                                         and predictions[key].prediction.value is not None))
        facts.append(MetricFact(
            **base, definition_id="regression.residuals", value_type="series", value=series, unit=unit,
            direction="none", state="missing" if not n else "error" if overflow else "measured",
            reason="no_valid_pairs" if not n else "numeric_overflow" if overflow else None,
            aggregation={"method": "identity", "normalization_count": None},
        ))
    return facts


def evaluate_task(snapshot: SnapshotContent, rows: tuple[PredictionRow, ...], manifest=None):
    """One shared result for future transports; no quality policy implies no pass/fail."""
    from app.domain.tasks.contracts import EvaluatorManifest, TaskResult, digest

    manifest = manifest or EvaluatorManifest()
    facts = evaluate(snapshot, rows, histogram_edges=manifest.config.histogram_edges)
    return TaskResult(
        snapshot_hash=snapshot.content_hash,
        prediction_hash=digest([row.model_dump(mode="json") for row in sorted(rows, key=lambda row: row.sample_id)]),
        config_hash=digest(manifest.model_dump(mode="json")), evaluator_manifest=manifest,
        n_total=facts[0].n_total, n_valid=facts[0].n_valid, coverage=facts[0].coverage, metrics=tuple(facts),
    )


def _residual_point(key, item, row):
    expected = item.expected_output
    valid = expected is not None and expected.value is not None
    return {"key": key, "x": row.prediction.value,
            "y": row.prediction.value - expected.value if valid else None,
            "state": "measured" if valid else "missing", "reason": None if valid else "missing_reference"}
