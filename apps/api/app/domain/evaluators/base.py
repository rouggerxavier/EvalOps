from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class EvaluatorResult:
    score: float          # 0..1
    passed: bool
    reasoning: str = ""
    raw_output: dict[str, Any] = field(default_factory=dict)
    cost_usd: float = 0.0
    latency_ms: int = 0
