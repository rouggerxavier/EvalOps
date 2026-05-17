from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
from queue import Empty, Full, Queue
import tempfile
from threading import Event, Thread
from time import sleep
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import httpx

logger = logging.getLogger(__name__)

DEAD_LETTER_VERSION = 1
DEAD_LETTER_ENV = "EVALOPS_DEAD_LETTER_DIR"
DEAD_LETTER_PREFIX = "evalops-dead-letter-"


@dataclass
class UploaderConfig:
    api_url: str
    api_key: str
    max_queue: int = 1024
    flush_interval: float = 2.0
    max_batch: int = 64
    timeout: float = 5.0
    max_retries: int = 2
    retry_backoff_s: float = 0.2
    submit_timeout_s: float = 0.05
    dead_letter_dir: str | Path | None = None


@dataclass
class ReplayResult:
    files_seen: int = 0
    replayed: int = 0
    failed: int = 0
    removed: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def attempted_files(self) -> int:
        return self.files_seen

    @property
    def replayed_files(self) -> int:
        return self.replayed

    @property
    def failed_files(self) -> int:
        return self.failed

    @property
    def skipped_files(self) -> int:
        return self.skipped

    @property
    def removed_files(self) -> int:
        return self.removed


@dataclass
class _SendOutcome:
    ok: bool
    should_dead_letter: bool = False
    http_status: int | None = None


def _dead_letter_dir(path: str | Path | None = None) -> Path:
    if path is not None:
        return Path(path).expanduser()
    env_path = os.getenv(DEAD_LETTER_ENV)
    if env_path:
        return Path(env_path).expanduser()
    return Path.home() / ".evalops" / "dead"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _api_url_metadata(api_url: str) -> str | None:
    try:
        parts = urlsplit(api_url)
    except ValueError:
        return None
    netloc = parts.netloc.rsplit("@", 1)[-1]
    return urlunsplit((parts.scheme, netloc, parts.path, "", ""))


def _safe_error(message: str, filename: str | None = None) -> str:
    if filename:
        return f"{filename}: {message}"
    return message


def _write_dead_letter(
    traces: list[dict[str, Any]],
    config: UploaderConfig,
    *,
    failure_kind: str,
    http_status: int | None = None,
) -> None:
    directory = _dead_letter_dir(config.dead_letter_dir)
    tmp_path: str | None = None
    try:
        directory.mkdir(parents=True, exist_ok=True)
        created_at = _utc_now()
        timestamp = created_at.replace(":", "").replace(".", "")
        final_name = f"{DEAD_LETTER_PREFIX}{timestamp}-{uuid4().hex}.json"
        final_path = directory / final_name
        payload: dict[str, Any] = {
            "version": DEAD_LETTER_VERSION,
            "created_at": created_at,
            "trace_count": len(traces),
            "failure_kind": failure_kind,
            "traces": traces,
        }
        api_url = _api_url_metadata(config.api_url)
        if api_url is not None:
            payload["api_url"] = api_url
        if http_status is not None:
            payload["http_status"] = http_status

        fd, tmp_path = tempfile.mkstemp(prefix=".evalops-dead-letter-", suffix=".tmp", dir=directory)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, separators=(",", ":"), sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, final_path)
        tmp_path = None
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "evalops sdk could not write dead-letter file for %s trace payload(s): %s",
            len(traces),
            exc.__class__.__name__,
        )
    finally:
        if tmp_path is not None:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def _send_traces(
    traces: list[dict[str, Any]],
    config: UploaderConfig,
) -> _SendOutcome:
    payload = {"traces": traces}
    headers = {"X-EvalOps-Key": config.api_key}
    attempt = 0
    last_status: int | None = None
    while attempt <= config.max_retries:
        try:
            with httpx.Client(timeout=config.timeout) as client:
                response = client.post(f"{config.api_url}/traces", headers=headers, json=payload)
            if 200 <= response.status_code < 300:
                return _SendOutcome(ok=True)
            last_status = response.status_code
            if response.status_code not in (408, 429) and response.status_code < 500:
                return _SendOutcome(ok=False, should_dead_letter=False, http_status=response.status_code)
        except Exception:
            last_status = None
        if attempt >= config.max_retries:
            return _SendOutcome(ok=False, should_dead_letter=True, http_status=last_status)
        sleep(config.retry_backoff_s * (2**attempt))
        attempt += 1
    return _SendOutcome(ok=False, should_dead_letter=False)


def _candidate_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    if not path.exists():
        return []
    if not path.is_dir():
        return []
    return sorted(
        p
        for p in path.iterdir()
        if p.is_file() and p.name.startswith(DEAD_LETTER_PREFIX) and p.suffix == ".json"
    )


def replay_dead_letter(
    path: str | Path | None = None,
    *,
    api_url: str,
    api_key: str,
    dead_letter_dir: str | Path | None = None,
    timeout: float = 5.0,
    max_retries: int = 2,
    retry_backoff_s: float = 0.2,
) -> ReplayResult:
    if path is not None and dead_letter_dir is not None:
        return ReplayResult(errors=["path and dead_letter_dir cannot both be set"])
    target = Path(path).expanduser() if path is not None else _dead_letter_dir(dead_letter_dir)
    config = UploaderConfig(
        api_url=api_url.rstrip("/"),
        api_key=api_key,
        timeout=timeout,
        max_retries=max_retries,
        retry_backoff_s=retry_backoff_s,
    )
    result = ReplayResult(errors=[])
    for file_path in _candidate_files(target):
        result.files_seen += 1
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            result.skipped += 1
            result.errors.append(_safe_error(f"invalid JSON ({exc.__class__.__name__})", file_path.name))
            continue
        if not isinstance(data, dict) or data.get("version") != DEAD_LETTER_VERSION:
            result.skipped += 1
            result.errors.append(_safe_error("unsupported dead-letter version", file_path.name))
            continue
        traces = data.get("traces")
        if not isinstance(traces, list):
            result.skipped += 1
            result.errors.append(_safe_error("missing traces", file_path.name))
            continue
        if not _send_traces(traces, config).ok:
            result.failed += 1
            result.errors.append(_safe_error("replay send failed", file_path.name))
            continue
        result.replayed += 1
        try:
            file_path.unlink()
            result.removed += 1
        except OSError as exc:
            result.errors.append(_safe_error(f"remove failed ({exc.__class__.__name__})", file_path.name))
    return result


class BackgroundUploader:
    def __init__(self, config: UploaderConfig) -> None:
        self.config = config
        self.queue: Queue[dict[str, Any]] = Queue(maxsize=config.max_queue)
        self._stop = Event()
        self._dropped = 0
        self._thread = Thread(target=self._loop, daemon=True)
        self._thread.start()

    def submit(self, trace_payload: dict[str, Any]) -> None:
        try:
            self.queue.put(trace_payload, timeout=self.config.submit_timeout_s)
        except Full:
            # Queue full: fallback to direct send so payload is not dropped
            # silently. If it still fails after retries, count as dropped.
            outcome = self._send_with_outcome([trace_payload])
            if not outcome.ok:
                self._write_dead_letter_for_outcome([trace_payload], outcome)
                self._dropped += 1
                logger.warning("evalops sdk dropped trace payload after queue-full fallback")

    def flush(self) -> None:
        while self._send_buffered(requeue_on_failure=False):
            pass

    def shutdown(self) -> None:
        self._stop.set()
        join_timeout = self._shutdown_join_timeout()
        self._thread.join(timeout=join_timeout)
        if self._thread.is_alive():
            logger.warning("evalops sdk background uploader did not stop within %.2fs", join_timeout)
            return
        self.flush()

    @property
    def dropped_count(self) -> int:
        return self._dropped

    def _shutdown_join_timeout(self) -> float:
        retries = max(0, self.config.max_retries)
        attempts = retries + 1
        retry_backoff = max(0.0, self.config.retry_backoff_s)
        backoff_budget = sum(retry_backoff * (2**attempt) for attempt in range(retries))
        request_budget = attempts * max(0.0, self.config.timeout)
        return max(1.0, request_budget + backoff_budget + 0.1)

    def _send_buffered(self, requeue_on_failure: bool = True) -> bool:
        buf: list[dict[str, Any]] = []
        while len(buf) < self.config.max_batch:
            try:
                buf.append(self.queue.get_nowait())
            except Empty:
                break
        if not buf:
            return False
        outcome = self._send_with_outcome(buf)
        if not outcome.ok:
            # Do not requeue once shutdown started: a final failed send during
            # shutdown must be counted as dropped on this first failure path so
            # shutdown() does not need a second _send() within the budget.
            if requeue_on_failure and not self._stop.is_set():
                self._requeue(buf)
            else:
                self._write_dead_letter_for_outcome(buf, outcome)
                self._dropped += len(buf)
                logger.warning("evalops sdk dropped %s trace payload(s) after final send failure", len(buf))
        return True

    def _loop(self) -> None:
        while not self._stop.is_set():
            sent = self._send_buffered()
            if not sent:
                self._stop.wait(self.config.flush_interval)
        while self._send_buffered(requeue_on_failure=False):
            pass

    def _requeue(self, traces: list[dict[str, Any]]) -> None:
        for trace_payload in traces:
            try:
                self.queue.put_nowait(trace_payload)
            except Full:
                self._dropped += 1
                logger.warning("evalops sdk dropped trace payload while requeueing failed batch")

    def _send_with_outcome(self, traces: list[dict[str, Any]]) -> _SendOutcome:
        return _send_traces(traces, self.config)

    def _send(self, traces: list[dict[str, Any]]) -> bool:
        outcome = self._send_with_outcome(traces)
        if not outcome.ok:
            self._write_dead_letter_for_outcome(traces, outcome)
        return outcome.ok

    def _write_dead_letter_for_outcome(self, traces: list[dict[str, Any]], outcome: _SendOutcome) -> None:
        if not outcome.should_dead_letter:
            return
        _write_dead_letter(
            traces,
            self.config,
            failure_kind="retry_exhausted",
            http_status=outcome.http_status,
        )
