"""Automatic failure rules shared by evaluation execution and quality reporting."""


def automatic_failures(scores: list, conditions: list[dict]) -> list[str]:
    by_slug = {score.evaluator_slug: score for score in scores}
    return [
        condition["slug"]
        for condition in conditions
        if condition.get("evaluator_id") in by_slug
        and not by_slug[condition["evaluator_id"]].passed
    ]
