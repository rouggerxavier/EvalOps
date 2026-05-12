"""Strict YAML parser and Pydantic validator for rubric specs."""
from __future__ import annotations

import re
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator


VALID_EVALUATOR_TYPES = {
    "regex_match",
    "keyword_presence",
    "length_bounds",
    "json_schema_valid",
    "exact_match",
    "cosine_similarity",
    "llm_judge",
}

VALID_AGGREGATE_METHODS = {"weighted_mean", "mean", "min", "max"}

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")

# Top-level fields allowed in YAML (unknown fields rejected)
_ALLOWED_TOP_FIELDS = {
    "slug", "name", "description", "version", "status", "threshold", "aggregate",
    "fail_fast", "evaluators", "judge", "thresholds", "criteria", "critical_flags",
    "automatic_fail_conditions", "cost_limits", "output_schema", "metadata",
    "evaluation_mode", "input_resolver", "output_resolver",
}


class EvaluatorSpec(BaseModel):
    id: str
    type: str
    weight: float = Field(default=1.0, gt=0)
    config: dict[str, Any] = Field(default_factory=dict)
    name: str | None = None
    enabled: bool = True
    criteria: list[str] = Field(default_factory=list)
    fail_fast: bool = False

    @field_validator("id")
    @classmethod
    def id_slug(cls, v: str) -> str:
        if not _SLUG_RE.match(v):
            raise ValueError(f"evaluator id '{v}' must be snake-case/kebab-case")
        return v

    @field_validator("type")
    @classmethod
    def valid_type(cls, v: str) -> str:
        if v not in VALID_EVALUATOR_TYPES:
            raise ValueError(f"unknown evaluator type '{v}'; must be one of {sorted(VALID_EVALUATOR_TYPES)}")
        return v


class CriterionSpec(BaseModel):
    slug: str
    name: str
    description: str = ""
    weight: float = 1.0
    scale: str = "0-1"
    required: bool = False
    evaluator: str = ""
    pass_threshold: float = 0.5
    metadata: dict[str, Any] = Field(default_factory=dict)


class CriticalFlagSpec(BaseModel):
    slug: str
    description: str
    severity: Literal["low", "medium", "high", "critical"] = "high"
    auto_fail: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class AutoFailConditionSpec(BaseModel):
    slug: str
    description: str
    evaluator_id: str | None = None
    flag: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def has_target(self) -> "AutoFailConditionSpec":
        if self.evaluator_id is None and self.flag is None:
            raise ValueError("automatic_fail_conditions entry must have 'evaluator_id' or 'flag'")
        return self


class RubricSpec(BaseModel):
    slug: str
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    threshold: float = Field(ge=0.0, le=1.0, default=0.7)
    aggregate: str = "weighted_mean"
    evaluators: list[EvaluatorSpec] = Field(min_length=1)
    version: int | None = None
    status: Literal["draft", "active", "archived"] = "draft"
    fail_fast: bool = False
    judge: dict[str, Any] = Field(default_factory=dict)
    thresholds: dict[str, Any] = Field(default_factory=dict)
    criteria: list[CriterionSpec] = Field(default_factory=list)
    critical_flags: list[CriticalFlagSpec] = Field(default_factory=list)
    automatic_fail_conditions: list[AutoFailConditionSpec] = Field(default_factory=list)
    cost_limits: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    evaluation_mode: dict[str, Any] = Field(default_factory=dict)
    input_resolver: str = "auto"
    output_resolver: str = "auto"

    @field_validator("slug")
    @classmethod
    def slug_format(cls, v: str) -> str:
        if not _SLUG_RE.match(v):
            raise ValueError(f"slug '{v}' must be snake-case/kebab-case")
        return v

    @field_validator("aggregate")
    @classmethod
    def valid_aggregate(cls, v: str) -> str:
        if v not in VALID_AGGREGATE_METHODS:
            raise ValueError(f"aggregate must be one of {sorted(VALID_AGGREGATE_METHODS)}")
        return v

    @model_validator(mode="after")
    def validate_evaluator_ids_unique(self) -> "RubricSpec":
        seen: set[str] = set()
        for ev in self.evaluators:
            if ev.id in seen:
                raise ValueError(f"duplicate evaluator id '{ev.id}'")
            seen.add(ev.id)
        return self

    @model_validator(mode="after")
    def validate_criteria_refs(self) -> "RubricSpec":
        criteria_slugs = {c.slug for c in self.criteria}
        for ev in self.evaluators:
            for crit_ref in ev.criteria:
                if criteria_slugs and crit_ref not in criteria_slugs:
                    raise ValueError(f"evaluator '{ev.id}' references unknown criterion '{crit_ref}'")
        return self

    @model_validator(mode="after")
    def validate_auto_fail_refs(self) -> "RubricSpec":
        evaluator_ids = {ev.id for ev in self.evaluators}
        flag_slugs = {f.slug for f in self.critical_flags}
        for cond in self.automatic_fail_conditions:
            if cond.evaluator_id and cond.evaluator_id not in evaluator_ids:
                raise ValueError(
                    f"automatic_fail_condition '{cond.slug}' references unknown evaluator '{cond.evaluator_id}'"
                )
            if cond.flag and cond.flag not in flag_slugs:
                raise ValueError(
                    f"automatic_fail_condition '{cond.slug}' references unknown flag '{cond.flag}'"
                )
        return self

    @model_validator(mode="after")
    def validate_weighted_mean_weights(self) -> "RubricSpec":
        if self.aggregate == "weighted_mean":
            for ev in self.evaluators:
                if ev.enabled and ev.weight <= 0:
                    raise ValueError(f"evaluator '{ev.id}' weight must be > 0 for weighted_mean")
        return self


def parse_rubric_yaml(yaml_source: str) -> RubricSpec:
    """Parse and validate rubric YAML. Raises ValueError with details on failure."""
    try:
        raw = yaml.safe_load(yaml_source)
    except yaml.YAMLError as exc:
        raise ValueError(f"YAML parse error: {exc}") from exc

    if not isinstance(raw, dict):
        raise ValueError("YAML must be a mapping/object at the top level")

    unknown = set(raw.keys()) - _ALLOWED_TOP_FIELDS
    if unknown:
        raise ValueError(f"unknown top-level fields: {sorted(unknown)}")

    try:
        return RubricSpec.model_validate(raw)
    except Exception as exc:
        raise ValueError(str(exc)) from exc
