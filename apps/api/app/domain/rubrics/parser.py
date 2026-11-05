"""Strict YAML parser and Pydantic validator for rubric specs."""
from __future__ import annotations

import re
from typing import Any, Literal

import jsonschema
import jinja2
import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

from app.domain.rubrics.templating import check_template


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


# A wrong path resolves to "" at run time, so it is rejected when the rubric is saved.
_TARGET_PATHS = {
    "trace.id", "trace.name", "trace.status", "trace.user_ref",
    "trace.input.text", "trace.input.user_message",
    "trace.output.text", "trace.output.assistant_message",
    "trace.conversation.id", "trace.conversation.transcript",
}
_TARGET_PREFIXES = ("trace.metadata.", "trace.tags.", "dataset_item.expected_output.", "variant.")
_TARGET_KEYS = {
    "regex_match": ("target",),
    "keyword_presence": ("target",),
    "length_bounds": ("target",),
    "json_schema_valid": ("target",),
    "exact_match": ("target",),
    "cosine_similarity": ("target_a",),
}
_CHOICES = {
    "regex_match": {"mode": ("must_match", "must_not_match")},
    "keyword_presence": {"require": ("any", "all", "none")},
    "length_bounds": {"unit": ("chars", "words", "tokens")},
    "json_schema_valid": {"parse_mode": ("strict", "extract_first")},
}
_TEMPLATE_KEYS = {"exact_match": ("expected",), "cosine_similarity": ("target_b",), "llm_judge": ("prompt",)}
_LENGTH_KEYS = ("min", "max", "min_chars", "max_chars", "min_words", "max_words")
MAX_JUDGE_REPEATS = 5


def _validate_evaluator_config(evaluator_type: str, config: dict[str, Any]) -> None:
    for key in _TARGET_KEYS.get(evaluator_type, ()):
        target = config.get(key)
        if not isinstance(target, str) or not (target in _TARGET_PATHS or target.startswith(_TARGET_PREFIXES)):
            raise ValueError(f"{evaluator_type}.{key} must be a known path such as trace.output.text")
    for key, allowed in _CHOICES.get(evaluator_type, {}).items():
        if key in config and config[key] not in allowed:
            raise ValueError(f"{evaluator_type}.{key} must be one of {allowed}")
    for key in _TEMPLATE_KEYS.get(evaluator_type, ()):
        template = config.get(key)
        if not isinstance(template, str) or not template.strip():
            raise ValueError(f"{evaluator_type}.{key} is required")
        try:
            check_template(template)
        except jinja2.TemplateError as exc:
            raise ValueError(f"{evaluator_type}.{key} is not a valid template") from exc

    if evaluator_type == "regex_match":
        try:
            re.compile(config.get("pattern") or "")
        except re.error as exc:
            raise ValueError("regex_match.pattern is not a valid regex") from exc
        if not config.get("pattern"):
            raise ValueError("regex_match.pattern is required")
    elif evaluator_type == "keyword_presence":
        keywords = config.get("keywords")
        if not keywords or not isinstance(keywords, list) or not all(isinstance(k, str) and k for k in keywords):
            raise ValueError("keyword_presence.keywords must be a non-empty list of strings")
    elif evaluator_type == "length_bounds":
        if not any(config.get(key) is not None for key in _LENGTH_KEYS):
            raise ValueError("length_bounds needs a min or max")
    elif evaluator_type == "json_schema_valid" and config.get("schema"):
        try:
            jsonschema.validators.validator_for(config["schema"]).check_schema(config["schema"])
        except jsonschema.SchemaError as exc:
            raise ValueError("json_schema_valid.schema is not a valid JSON schema") from exc
    elif evaluator_type == "llm_judge":
        repeats = config.get("repeats", 1)
        if not isinstance(repeats, int) or isinstance(repeats, bool) or not 1 <= repeats <= MAX_JUDGE_REPEATS:
            raise ValueError(f"llm_judge.repeats must be between 1 and {MAX_JUDGE_REPEATS}")


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

    @model_validator(mode="after")
    def valid_config(self) -> "EvaluatorSpec":
        _validate_evaluator_config(self.type, self.config)
        return self


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
    def validate_flags_have_a_source(self) -> "RubricSpec":
        # Only llm_judge reports flags: without one the rule would silently never fire.
        uses_flags = any(cond.flag for cond in self.automatic_fail_conditions) or any(
            flag.auto_fail for flag in self.critical_flags
        )
        if uses_flags and not any(ev.type == "llm_judge" and ev.enabled for ev in self.evaluators):
            raise ValueError("automatic failure by flag needs an enabled llm_judge evaluator")
        return self

    @model_validator(mode="after")
    def validate_weighted_mean_weights(self) -> "RubricSpec":
        if self.aggregate == "weighted_mean":
            for ev in self.evaluators:
                if ev.enabled and ev.weight <= 0:
                    raise ValueError(f"evaluator '{ev.id}' weight must be > 0 for weighted_mean")
        return self


def ignored_fields(spec: RubricSpec) -> list[str]:
    """Fields accepted for compatibility that no evaluation path reads."""
    ignored = [
        name for name in ("judge", "thresholds", "criteria", "cost_limits", "output_schema", "evaluation_mode")
        if getattr(spec, name)
    ]
    ignored += [name for name in ("input_resolver", "output_resolver") if getattr(spec, name) != "auto"]
    return ignored


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
