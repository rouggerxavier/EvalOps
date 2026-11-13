"""Aggregate-only deletion inventory; no execution contract is implied."""
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class DeletionDependency(BaseModel):
    code: str
    count: int
    organization_id: str | None = None


class DeletionMembership(BaseModel):
    organization_id: str
    role: str
    last_owner: bool


class DeletionCost(BaseModel):
    period: str
    source: str
    known_cost_usd: Decimal
    unknown_cost_records: int = 0


class DeletionPreview(BaseModel):
    scope: Literal["project", "organization", "account"]
    target_id: str
    execution_available: Literal[False] = False
    resource_counts: dict[str, int]
    api_keys: dict[str, int] = Field(default_factory=dict)
    managed_file_references: int = 0
    memberships: list[DeletionMembership] = Field(default_factory=list)
    dependencies: list[DeletionDependency] = Field(default_factory=list)
    known_costs: list[DeletionCost] = Field(default_factory=list)
    excluded_scopes: list[str]
    limitations: list[str]
