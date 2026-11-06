"""Shared analytics conventions for overview and project quality gates."""
import math
from datetime import datetime, timedelta

from app.models import utcnow


def p95_nearest_rank(values: list[int | float]) -> int | float:
    if not values:
        return 0
    sorted_values = sorted(values)
    n = len(sorted_values)
    index = min(n - 1, max(0, math.ceil(0.95 * n) - 1))
    return sorted_values[index]


_OVERVIEW_WINDOW_TO_TIMEDELTA: dict[str, timedelta] = {
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}


def resolve_overview_cutoff(window: str | None, limit_days: int) -> tuple[datetime, int | None]:
    """Resolve the overview cutoff timestamp and an optional day-cap.

    ``window`` takes precedence over ``limit_days``. When ``window`` is set the
    cutoff itself bounds ``cost_by_day`` (no additional ``LIMIT``) so the daily
    series sums back to the same trace universe as the KPIs — a 24 h window
    crossing midnight still returns two calendar-day buckets, matching the
    KPI ``traces`` count. ``limit_days`` callers keep the legacy bucket cap.
    """
    if window in _OVERVIEW_WINDOW_TO_TIMEDELTA:
        delta = _OVERVIEW_WINDOW_TO_TIMEDELTA[window]
        return utcnow() - delta, None
    days = max(1, min(limit_days, 90))
    return utcnow() - timedelta(days=days), days
