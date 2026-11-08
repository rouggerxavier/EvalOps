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

    def _request(self, method: str, path: str, *, payload: dict | None = None) -> dict[str, Any]:
        config = self._config
        # Feedback has no idempotency key: retrying a timed-out POST can duplicate it.
        attempts = config.max_retries + 1 if method == "GET" else 1
        for attempt in range(attempts):
            try:
                with httpx.Client(timeout=config.timeout) as client:
                    response = client.request(
                        method, f"{config.api_url}{path}", headers={"X-EvalOps-Key": config.api_key}, json=payload
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
