"""Dispatch a sealed evaluator manifest by task; transports consume persisted results."""
from fastapi import HTTPException
from app.domain.tasks import classification, regression


def evaluate_task(snapshot, rows, manifest):
    task = snapshot.task_schema.task_type
    if manifest.id != f"{task}.standard":
        raise HTTPException(422, "evaluator_task_mismatch")
    return (classification if task == "classification" else regression).evaluate_task(snapshot, rows, manifest)
