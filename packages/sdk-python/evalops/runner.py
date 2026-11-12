"""Runner-scoped HTTP identity. It cannot inherit ordinary API read/write methods."""
from __future__ import annotations

from evalops.client import _HttpClient, _path_id
from evalops.uploader import DEFAULT_TIMEOUT_S


class RunnerClient(_HttpClient):
    _key_header = "X-EvalOps-Runner-Key"

    def __init__(self, *, runner_key: str, api_url: str = "http://localhost:8000/v1", timeout: float = DEFAULT_TIMEOUT_S):
        super().__init__(api_key=runner_key, api_url=api_url, timeout=timeout)

    def capabilities(self, runner_id: str):
        return self._request("GET", f"/runners/{_path_id(runner_id)}/capabilities")

    def claim(self, runner_id: str, *, idempotency_key: str):
        """Lease the next queued execution or return None. Replaying the same key re-issues the token while valid until the first heartbeat."""
        return self._request("POST", f"/runners/{_path_id(runner_id)}/leases", idempotency_key=idempotency_key)["lease"]

    def _attempt(self, lease: dict, action: str, payload: dict | None = None):
        path = f"/executions/{_path_id(lease['execution_id'])}/attempts/{_path_id(lease['attempt_id'])}/{action}"
        return self._request("POST", path, payload=payload, headers={"X-EvalOps-Lease-Token": lease["lease_token"]})

    def heartbeat(self, lease: dict):
        """Renew every heartbeat_interval_s up to wall_time_s; stop work on cancel_requested or any HTTP error."""
        return self._attempt(lease, "heartbeat")

    def complete(self, lease: dict, report: dict):
        """Terminal report; cost {"state": "unknown"} keeps the budget hold instead of counting as zero."""
        return self._attempt(lease, "complete", report)
