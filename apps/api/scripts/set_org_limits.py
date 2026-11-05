"""Set one organization's monthly limits. Operator-only: there is no HTTP route for this.

Usage (from apps/api, with DATABASE_URL set):
    python scripts/set_org_limits.py --org my-org --traces 100000 --evals 20000
"""
import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from app.db import SessionLocal
from app.domain.services.audit_service import record_audit
from app.domain.services.usage_service import set_org_plan_limits
from app.models import Organization

# Plan and usage counter columns are 32-bit integers.
MAX_LIMIT = 2_147_483_647
COLUMNS = {
    "traces": "monthly_trace_limit",
    "evals": "monthly_eval_limit",
    "exports": "monthly_export_limit",
    "spans": "monthly_span_limit",
    "tokens": "monthly_token_limit",
}


def _limit(raw: str) -> int:
    value = int(raw)
    if not 0 < value <= MAX_LIMIT:
        raise argparse.ArgumentTypeError(f"must be between 1 and {MAX_LIMIT}")
    return value


def _budget(raw: str) -> float:
    value = float(raw)
    if not 0 < value < float("inf"):
        raise argparse.ArgumentTypeError("must be a positive number")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--org", required=True, help="organization slug")
    for flag in COLUMNS:
        parser.add_argument(f"--{flag}", type=_limit)
    parser.add_argument("--judge-budget-usd", type=_budget)
    args = parser.parse_args()

    limits = {column: getattr(args, flag) for flag, column in COLUMNS.items() if getattr(args, flag) is not None}
    if args.judge_budget_usd is not None:
        limits["monthly_judge_budget_usd"] = args.judge_budget_usd
    if not limits:
        parser.error("pass at least one limit")

    with SessionLocal() as db:
        org = db.query(Organization).filter(Organization.slug == args.org).one_or_none()
        if org is None:
            print(f"organization not found: {args.org}", file=sys.stderr)
            return 1
        set_org_plan_limits(db, org.id, **limits)
        record_audit(
            db, "plan.limits_changed",
            organization_id=org.id,
            target_type="organization",
            target_id=org.id,
            payload=limits,
        )
        db.commit()
    print(f"{args.org}: {limits}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
