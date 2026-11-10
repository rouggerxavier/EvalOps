"""Immutable value contracts; no dependency on tracing or provider runtimes."""
from __future__ import annotations

import hashlib
import json
import math
import sys
from typing import Annotated, Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt, model_validator

Environment = Literal["dev", "staging", "prod"]
FiniteInteger = Annotated[StrictInt, Field(ge=-int(sys.float_info.max), le=int(sys.float_info.max))]
Number = FiniteInteger | StrictFloat
Count = Annotated[StrictInt, Field(ge=0, le=int(sys.float_info.max))]


def canonical_json(value: Any) -> str:
    def check(current):
        if type(current) in (int, float):
            try:
                finite = math.isfinite(current)
            except OverflowError:
                finite = False
            if not finite:
                raise ValueError("nonfinite_json_number")
        elif isinstance(current, dict):
            for item in current.values():
                check(item)
        elif isinstance(current, (list, tuple)):
            for item in current:
                check(item)
    check(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    # Typed numeric fields already validate finitude; only arbitrary JSON needs a recursive check.
    json_fields: ClassVar[tuple[str, ...]] = ()

    @model_validator(mode="after")
    def finite_json(self):
        for name in self.json_fields:
            canonical_json(getattr(self, name))
        return self


class AccessLabel(Contract):
    label_schema_version: Literal[1] = 1
    origin_environments: tuple[Environment, ...]
    allowed_environments: tuple[Environment, ...]
    source_refs: tuple[str, ...] = ()
    access_revision: Annotated[StrictInt, Field(ge=1)] = 1

    @model_validator(mode="after")
    def unique_environments(self):
        if not self.allowed_environments:
            raise ValueError("empty_allowed_environments")
        for values in (self.origin_environments, self.allowed_environments, self.source_refs):
            if len(set(values)) != len(values):
                raise ValueError("duplicate_access_label_entry")
        return self


class Target(Contract):
    name: str = Field(min_length=1, max_length=255)
    unit: str = Field(min_length=1, max_length=64)


class RegressionSchema(Contract):
    task_type: Literal["regression"] = "regression"
    target: Target
    segments: tuple[str, ...] = Field(default=(), max_length=8)

    @model_validator(mode="after")
    def unique_segments(self):
        if any(not key or len(key) > 128 for key in self.segments) or len(set(self.segments)) != len(self.segments):
            raise ValueError("invalid_segments")
        return self


class Scalar(Contract):
    value: Number | None = None


class SnapshotItem(Contract):
    json_fields: ClassVar[tuple[str, ...]] = ('input', 'metadata')
    sample_id: str = Field(min_length=1, max_length=255)
    input: dict[str, Any]
    expected_output: Scalar | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    reference_status: Literal["draft", "reviewed", "rejected"] = "draft"


class SnapshotContent(Contract):
    schema_version: Literal[1] = 1
    canonicalizer_version: Literal[1] = 1
    task_schema: RegressionSchema
    items: tuple[SnapshotItem, ...] = Field(max_length=10000)

    @model_validator(mode="after")
    def unique_samples(self):
        if len({item.sample_id for item in self.items}) != len(self.items):
            raise ValueError("duplicate_sample_id")
        groups = set()
        for segment in self.task_schema.segments:
            for item in self.items:
                value = item.metadata.get(segment, "__missing__")
                if len(canonical_json({"segment": segment, "value": value}).encode("utf-8")) > 2048:
                    raise ValueError("segment_group_key_too_large")
                groups.add((segment, canonical_json(value)))
                if len(groups) > 1000:
                    raise ValueError("max_segment_groups_exceeded")
        return self

    def canonical_content(self) -> dict:
        content = self.model_dump(mode="json")
        content["items"].sort(key=lambda row: row["sample_id"])
        return content

    @property
    def content_hash(self) -> str:
        return digest(self.canonical_content())

    def materialize(self) -> str:
        """Persist this string, never a reference to mutable nested input dictionaries."""
        return canonical_json(self.canonical_content())


class PredictionRow(Contract):
    sample_id: str = Field(min_length=1, max_length=255)
    prediction: Scalar | None = None
    error: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def exclusive_result(self):
        if self.error is not None and self.prediction is not None:
            raise ValueError("prediction_and_error")
        return self


class Aggregation(Contract):
    method: Literal["mean", "root_mean", "r2", "count", "identity"]
    normalization_count: Count | None = None


class Quantity(Contract):
    value: Number
    unit: str


class Axis(Contract):
    name: str = Field(min_length=1)
    unit: str = Field(min_length=1)


class SeriesPoint(Contract):
    key: str = Field(min_length=1)
    x: Number
    y: Number | None
    state: Literal["measured", "missing", "not_applicable", "error"]
    reason: str | None

    @model_validator(mode="after")
    def valid_state(self):
        if self.state == "measured":
            if self.y is None or self.reason is not None:
                raise ValueError("invalid_measured_point")
        elif self.y is not None or not self.reason:
            raise ValueError("invalid_missing_point")
        return self


class Series(Contract):
    x_axis: Axis
    y_axis: Axis
    points: tuple[SeriesPoint, ...]

    @model_validator(mode="after")
    def unique_keys(self):
        if len({point.key for point in self.points}) != len(self.points):
            raise ValueError("duplicate_point_key")
        return self


class LabelAxis(Contract):
    name: str = Field(min_length=1)
    labels: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_labels(self):
        if any(not label for label in self.labels) or len(set(self.labels)) != len(self.labels):
            raise ValueError("invalid_axis_labels")
        return self


class Matrix(Contract):
    row_axis: LabelAxis
    column_axis: LabelAxis
    cells: tuple[tuple[Count, ...], ...]

    @model_validator(mode="after")
    def rectangular(self):
        if len(self.cells) != len(self.row_axis.labels) or any(len(row) != len(self.column_axis.labels) for row in self.cells):
            raise ValueError("invalid_matrix_dimensions")
        return self


class MetricFact(Contract):
    id: str | None = None
    task_evaluation_id: str | None = None
    schema_version: Literal[1] = 1
    definition_id: Literal["regression.mae", "regression.mse", "regression.rmse", "regression.r2", "regression.residuals", "classification.confusion", "regression.residual_histogram"]
    definition_version: Literal["1"] = "1"
    scope: Literal["sample", "dataset", "group", "model_version"] = "dataset"
    scope_key: str = "all"
    value_type: Literal["scalar", "series", "matrix"]
    value: Number | Series | Matrix | None
    unit: str = Field(min_length=1)
    direction: Literal["minimize", "maximize", "none"]
    state: Literal["measured", "missing", "not_applicable", "error"]
    reason: str | None
    population_unit: Literal["sample"] = "sample"
    n_total: Count
    n_valid: Count
    coverage: Number | None
    aggregation: Aggregation
    statistics: dict[str, Quantity] = Field(default_factory=dict)
    evidence_refs: tuple[str, ...] = ()

    @model_validator(mode="after")
    def definition_contract(self):
        if self.definition_id in {"classification.confusion", "regression.residual_histogram"}:
            if (self.value_type != "matrix" or self.unit != "count" or self.direction != "none"
                    or self.aggregation.method != "count" or self.aggregation.normalization_count is not None
                    or self.statistics or self.n_valid > self.n_total
                    or self.coverage != (self.n_valid / self.n_total if self.n_total else None)):
                raise ValueError("invalid_confusion_definition")
            if self.state == "measured":
                if not isinstance(self.value, Matrix) or self.reason is not None or not self.n_valid:
                    raise ValueError("invalid_measured_matrix")
                axes = (self.value.row_axis.name, self.value.column_axis.name)
                expected_axes = ("actual", "predicted") if self.definition_id == "classification.confusion" else ("residual_interval", "count")
                if axes != expected_axes:
                    raise ValueError("invalid_matrix_axes")
                if sum(sum(row) for row in self.value.cells) != self.n_valid:
                    raise ValueError("invalid_confusion_population")
            elif self.value is not None or not self.reason:
                raise ValueError("invalid_unmeasured_matrix")
            return self
        kind = self.definition_id.removeprefix("regression.")
        method = {"mae": "mean", "mse": "mean", "rmse": "root_mean", "r2": "r2", "residuals": "identity"}[kind]
        direction = "maximize" if kind == "r2" else "none" if kind == "residuals" else "minimize"
        if self.direction != direction or self.aggregation.method != method:
            raise ValueError("definition_mismatch")
        if self.n_valid > self.n_total:
            raise ValueError("invalid_population")
        expected_coverage = self.n_valid / self.n_total if self.n_total else None
        if self.coverage != expected_coverage:
            raise ValueError("invalid_coverage")
        normalizer = self.n_valid if method in ("mean", "root_mean") and self.n_valid else None
        if self.aggregation.normalization_count != normalizer:
            raise ValueError("invalid_normalization_count")
        if self.value_type != ("series" if kind == "residuals" else "scalar"):
            raise ValueError("invalid_value_type")
        if self.state == "measured":
            if self.value is None or self.reason is not None:
                raise ValueError("invalid_measured_value")
            if kind == "residuals":
                if not isinstance(self.value, Series) or self.value.y_axis.unit != self.unit:
                    raise ValueError("invalid_series")
                if (self.value.x_axis.unit != self.unit or self.value.x_axis.name != "prediction"
                        or self.value.y_axis.name != "residual" or not self.n_valid
                        or sum(point.state == "measured" for point in self.value.points) != self.n_valid
                        or len(self.value.points) > self.n_total):
                    raise ValueError("invalid_residual_population")
            elif type(self.value) not in (int, float):
                raise ValueError("invalid_scalar")
            elif not self.n_valid or (kind in {"mae", "mse", "rmse"} and self.value < 0):
                raise ValueError("invalid_scalar_population_or_range")
        elif self.value is not None or not self.reason:
            raise ValueError("invalid_unmeasured_value")
        if kind == "r2":
            if self.unit != "1":
                raise ValueError("invalid_r2_unit")
            if self.n_valid and self.state in ("measured", "not_applicable"):
                if set(self.statistics) != {"sse", "sst", "target_mean"}:
                    raise ValueError("invalid_r2_statistics")
                target_unit = self.statistics["target_mean"].unit
                if any(self.statistics[key].unit != target_unit + "^2" for key in ("sse", "sst")):
                    raise ValueError("invalid_statistics_unit")
        elif self.statistics:
            raise ValueError("unexpected_statistics")
        if kind == "mse" and not self.unit.endswith("^2"):
            raise ValueError("invalid_squared_unit")
        return self


class ModelVersionContent(Contract):
    json_fields: ClassVar[tuple[str, ...]] = ('config',)
    name: str = Field(min_length=1, max_length=255)
    version_ref: str = Field(min_length=1, max_length=255)
    task_type: Literal["regression"] = "regression"
    source_kind: Literal["external"] = "external"
    external_ref: str | None = None
    artifact_digest: str | None = None
    provenance: Literal["partial"] = "partial"
    config: dict[str, Any] = Field(default_factory=dict)

    @property
    def content_hash(self) -> str:
        return digest(self.model_dump(mode="json"))


class RegressionConfig(Contract):
    histogram_edges: tuple[Number, ...] = Field(default=(-100, -10, -1, 0, 1, 10, 100), min_length=2, max_length=50)

    @model_validator(mode="after")
    def ordered_edges(self):
        if any(left >= right for left, right in zip(self.histogram_edges, self.histogram_edges[1:])):
            raise ValueError("histogram_edges_must_increase")
        return self


class EvaluatorManifest(Contract):
    id: Literal["regression.standard"] = "regression.standard"
    version: Literal["1"] = "1"
    config: RegressionConfig = Field(default_factory=RegressionConfig)


class TaskResult(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["task_evaluation"] = "task_evaluation"
    status: Literal["succeeded"] = "succeeded"
    decision: Literal["inconclusive"] = "inconclusive"
    decision_reasons: tuple[Literal["no_quality_policy"], ...] = ("no_quality_policy",)
    evaluator_manifest: EvaluatorManifest = Field(default_factory=EvaluatorManifest)
    snapshot_hash: str
    prediction_hash: str
    config_hash: str
    n_total: Count
    n_valid: Count
    coverage: Number | None
    metrics: tuple[MetricFact, ...]

    @model_validator(mode="after")
    def consistent_population(self):
        if not self.metrics:
            raise ValueError("missing_metrics")
        for fact in self.metrics:
            if fact.scope == "dataset" and (fact.n_total, fact.n_valid, fact.coverage) != (
                    self.n_total, self.n_valid, self.coverage):
                raise ValueError("population_mismatch")
        if self.decision_reasons != ("no_quality_policy",):
            raise ValueError("missing_decision_reason")
        return self


class LabelDeclaration(Contract):
    environment: Environment
    independent: bool = False
    allowed_environments: tuple[Environment, ...] | None = None
    justification: str | None = None
    evidence: str | None = None

    @model_validator(mode="after")
    def valid_allowlist(self):
        if self.allowed_environments is not None and (not self.allowed_environments or len(set(self.allowed_environments)) != len(self.allowed_environments)):
            raise ValueError("invalid_allowed_environments")
        return self


class ModelCreate(Contract):
    model: ModelVersionContent
    access: LabelDeclaration


class TaskDatasetCreate(Contract):
    slug: str = Field(min_length=2, max_length=255, pattern=r"^[a-z0-9-]+$")
    description: str | None = None
    task_type: Literal["regression"]
    task_schema: RegressionSchema
    access: LabelDeclaration
    items: tuple[SnapshotItem, ...] = Field(default=(), max_length=10000)


class PredictionImport(Contract):
    json_fields: ClassVar[tuple[str, ...]] = ('producer_manifest',)
    snapshot_id: str
    model_version_id: str
    environment: Environment
    producer_manifest: dict[str, Any] = Field(default_factory=dict)
    rows: tuple[PredictionRow, ...] = Field(max_length=10000)


class EvaluationCreate(Contract):
    prediction_set_id: str
    evaluator: EvaluatorManifest = Field(default_factory=EvaluatorManifest)


class TaskVariant(Contract):
    name: str = Field(min_length=1, max_length=255)
    model_version_id: str


class TaskExperimentCreate(Contract):
    kind: Literal["task_comparison"]
    name: str = Field(min_length=2, max_length=255)
    dataset_id: str
    snapshot_id: str
    environment: Environment
    variants: tuple[TaskVariant, ...] = Field(min_length=2)


class ComparisonPolicy(Contract):
    json_fields: ClassVar[tuple[str, ...]] = ('critical_rules',)
    policy_version: Literal["1"] = "1"
    primary_metric: Literal["regression.mae@1", "regression.mse@1", "regression.rmse@1", "regression.r2@1"] = "regression.mae@1"
    max_degradation: Number = Field(default=0.0, ge=0)
    min_pairs: Annotated[StrictInt, Field(ge=1, le=int(sys.float_info.max))] = 30
    required_coverage: Number = Field(default=1.0, ge=0, le=1)
    critical_case_ids: tuple[str, ...] = ()
    critical_rules: tuple[dict[str, Any], ...] = ()
    confidence: None = None


class ComparisonCreate(Contract):
    baseline_evaluation_id: str
    candidate_evaluation_ids: tuple[str, ...] = Field(min_length=1)
    policy: ComparisonPolicy = Field(default_factory=ComparisonPolicy)
