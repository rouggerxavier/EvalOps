from __future__ import annotations

import math
from time import sleep
from typing import Any
from urllib.parse import quote

import httpx

from evalops.uploader import DEFAULT_TIMEOUT_S, UploaderConfig


def _path_id(value: str) -> str:
    if not value or value in {".", ".."}:
        raise ValueError("an id is required")
    return quote(value, safe="")


class Client:
    """Synchronous feedback and prompt requests, independent of the background tracer."""

    def __init__(
        self,
        *,
        api_key: str,
        api_url: str = "http://localhost:8000/v1",
        timeout: float = DEFAULT_TIMEOUT_S,
    ) -> None:
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be finite and positive")
        self._config = UploaderConfig(api_key=api_key, api_url=api_url.rstrip("/"), timeout=timeout)

    def _request(self, method: str, path: str, *, payload: dict | None = None, idempotency_key: str | None = None, if_match: str | None = None) -> dict[str, Any]:
        config = self._config
        # Feedback has no idempotency key: retrying a timed-out POST can duplicate it.
        attempts = config.max_retries + 1 if method == "GET" else 1
        for attempt in range(attempts):
            try:
                with httpx.Client(timeout=config.timeout) as client:
                    response = client.request(
                        method, f"{config.api_url}{path}", headers={"X-EvalOps-Key": config.api_key, **({"Idempotency-Key": idempotency_key} if idempotency_key else {}), **({"If-Match": if_match} if if_match else {})}, json=payload
                    )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as exc:
                code = exc.response.status_code
                if code not in (408, 429) and code < 500:
                    raise
                if attempt == attempts - 1:
                    raise
            except httpx.TransportError:
                if attempt == attempts - 1:
                    raise
            sleep(config.retry_backoff_s * (2**attempt))
        raise AssertionError("unreachable")

    def feedback(
        self,
        client_trace_id: str,
        *,
        thumbs: str | None = None,
        rating: int | None = None,
        comment: str | None = None,
        tags: list[str] | None = None,
        user_ref: str | None = None,
        correction: dict | None = None,
        source: str = "sdk",
    ) -> dict[str, Any]:
        """Send feedback for an already ingested client trace id; requires an ingest key."""
        payload = {
            "source": source, "thumbs": thumbs, "rating": rating, "comment": comment,
            "tags": tags if tags is not None else [], "user_ref": user_ref, "correction": correction,
        }
        return self._request(
            "POST", f"/traces/by-client-id/{_path_id(client_trace_id)}/feedback", payload=payload
        )["feedback"]

    def get_prompt(self, prompt_id: str, *, version: int | None = None) -> dict[str, Any]:
        """Fetch the current or numbered prompt version, including its template; requires read."""
        if version is not None and (isinstance(version, bool) or not isinstance(version, int) or version < 1):
            raise ValueError("version must be a positive integer")
        path = f"/prompts/{_path_id(prompt_id)}"
        if version is None:
            version = self._request("GET", path)["current_version"]
        versions = self._request("GET", f"{path}/versions")["data"]
        for row in versions:
            if row["version"] == version:
                return row
        raise LookupError(f"prompt version {version} not found")


    def discover(self, project_id: str) -> dict[str, Any]:
        return self._request("GET", f"/projects/{_path_id(project_id)}/capabilities")

    def create_task_dataset(self, project_id: str, payload: dict, *, idempotency_key: str) -> dict[str, Any]:
        return self._request("POST", f"/projects/{_path_id(project_id)}/datasets", payload=payload, idempotency_key=idempotency_key)

    def create_snapshot(self, dataset_id: str, *, environment: str, idempotency_key: str) -> dict[str, Any]:
        return self._request("POST", f"/datasets/{_path_id(dataset_id)}/snapshots", payload={"environment": environment}, idempotency_key=idempotency_key)

    def create_model_version(self, project_id: str, payload: dict, *, idempotency_key: str) -> dict[str, Any]:
        return self._request("POST", f"/projects/{_path_id(project_id)}/model-versions", payload=payload, idempotency_key=idempotency_key)

    def import_predictions(self, project_id: str, payload: dict, *, idempotency_key: str) -> dict[str, Any]:
        return self._request("POST", f"/projects/{_path_id(project_id)}/prediction-sets", payload=payload, idempotency_key=idempotency_key)

    def evaluate(self, project_id: str, prediction_set_id: str, *, idempotency_key: str) -> dict[str, Any]:
        return self._request("POST", f"/projects/{_path_id(project_id)}/task-evaluations", payload={"prediction_set_id": prediction_set_id, "evaluator": {"id": "regression.standard", "version": "1", "config": {}}}, idempotency_key=idempotency_key)

    def task_result(self, evaluation_id: str) -> dict[str, Any]:
        return self._request("GET", f"/task-evaluations/{_path_id(evaluation_id)}")

    def task_metrics(self, evaluation_id: str) -> dict[str, Any]:
        return self._request("GET", f"/task-evaluations/{_path_id(evaluation_id)}/metrics")

    def task_samples(self, evaluation_id: str, *, cursor: int = 0, limit: int = 100) -> dict[str, Any]:
        if type(cursor) is not int or cursor < 0 or type(limit) is not int or not 1 <= limit <= 500:
            raise ValueError("invalid pagination")
        return self._request("GET", f"/task-evaluations/{_path_id(evaluation_id)}/samples?cursor={cursor}&limit={limit}")

    def get_snapshot(self, snapshot_id: str) -> dict[str, Any]:
        return self._request("GET", f"/dataset-snapshots/{_path_id(snapshot_id)}")

    def get_model_version(self, model_id: str) -> dict[str, Any]:
        return self._request("GET", f"/model-versions/{_path_id(model_id)}")

    def list_task_evaluations(self, project_id: str) -> dict[str, Any]:
        return self._request("GET", f"/projects/{_path_id(project_id)}/task-evaluations")

    def create_task_experiment(self, project_id: str, payload: dict, *, idempotency_key: str) -> dict[str, Any]:
        return self._request("POST", f"/projects/{_path_id(project_id)}/experiments", payload=payload, idempotency_key=idempotency_key)

    def compare(self, experiment_id: str, payload: dict, *, idempotency_key: str) -> dict[str, Any]:
        return self._request("POST", f"/experiments/{_path_id(experiment_id)}/comparisons", payload=payload, idempotency_key=idempotency_key)

    def comparison_result(self, experiment_id: str, run_id: str) -> dict[str, Any]:
        return self._request("GET", f"/experiments/{_path_id(experiment_id)}/runs/{_path_id(run_id)}?view=task_v1")


    def create_investigation(self, project_id: str, payload: dict, *, idempotency_key: str) -> dict[str, Any]:
        return self._request("POST", f"/projects/{_path_id(project_id)}/investigations", payload=payload, idempotency_key=idempotency_key)

    def get_investigation(self, investigation_id: str) -> dict[str, Any]:
        return self._request("GET", f"/investigations/{_path_id(investigation_id)}")

    def investigation_history(self, investigation_id: str) -> dict[str, Any]:
        return self._request("GET", f"/investigations/{_path_id(investigation_id)}/revisions")

    def update_investigation(self, investigation_id: str, state: dict, *, revision: int, idempotency_key: str) -> dict[str, Any]:
        return self._request("PATCH", f"/investigations/{_path_id(investigation_id)}", payload={"state": state}, idempotency_key=idempotency_key, if_match=str(revision))

    def find_failures(self, project_id: str, *, kind: str = "trace") -> dict[str, Any]:
        if kind not in {"trace", "sample"}:
            raise ValueError("unknown failure kind")
        return self._request("GET", f"/projects/{_path_id(project_id)}/failures?kind={kind}")

    def get_trace_evidence(self, trace_id: str) -> dict[str, Any]:
        return self._request("GET", f"/task-evidence/traces/{_path_id(trace_id)}")

    def save_case(self, dataset_id: str, payload: dict, *, idempotency_key: str) -> dict[str, Any]:
        return self._request("POST", f"/datasets/{_path_id(dataset_id)}/cases", payload=payload, idempotency_key=idempotency_key)

    def get_case(self, dataset_id: str, item_id: str) -> dict[str, Any]:
        return self._request("GET", f"/datasets/{_path_id(dataset_id)}/items/{_path_id(item_id)}")

    def update_case(self, dataset_id: str, item_id: str, payload: dict, *, revision: int, idempotency_key: str) -> dict[str, Any]:
        return self._request("PATCH", f"/datasets/{_path_id(dataset_id)}/cases/{_path_id(item_id)}", payload=payload, idempotency_key=idempotency_key, if_match=str(revision))
