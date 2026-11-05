"""Automatic failure rules shared by evaluation execution and quality reporting."""


def automatic_failures(scores: list, conditions: list[dict]) -> list[str]:
    by_slug = {score.evaluator_slug: score for score in scores}
    return [
        condition["slug"]
        for condition in conditions
        if condition.get("evaluator_id") in by_slug
        and not by_slug[condition["evaluator_id"]].passed
    ]


def automatic_fail_flags(spec: dict) -> set[str]:
    return {
        flag["slug"] for flag in spec.get("critical_flags", []) if flag.get("auto_fail")
    } | {cond["flag"] for cond in spec.get("automatic_fail_conditions", []) if cond.get("flag")}


def raised_flags(scores: list) -> set[str]:
    raised: set[str] = set()
    for score in scores:
        flags = (score.raw_output or {}).get("flags")
        if isinstance(flags, list):
            raised.update(flag for flag in flags if isinstance(flag, str))
    return raised
