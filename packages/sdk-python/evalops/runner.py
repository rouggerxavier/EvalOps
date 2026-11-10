"""Runner-scoped HTTP identity. It cannot inherit ordinary API read/write methods."""
from evalops.client import _HttpClient, _path_id
from evalops.uploader import DEFAULT_TIMEOUT_S


class RunnerClient(_HttpClient):
    _key_header = "X-EvalOps-Runner-Key"

    def __init__(self, *, runner_key: str, api_url: str = "http://localhost:8000/v1", timeout: float = DEFAULT_TIMEOUT_S):
        super().__init__(api_key=runner_key, api_url=api_url, timeout=timeout)

    def capabilities(self, runner_id: str):
        return self._request("GET", f"/runners/{_path_id(runner_id)}/capabilities")
