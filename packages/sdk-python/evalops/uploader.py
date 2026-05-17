from __future__ import annotations

from dataclasses import dataclass
import logging
from queue import Empty, Full, Queue
from threading import Event, Thread
from time import sleep
from typing import Any

import httpx

logger = logging.getLogger(__name__)


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
            if not self._send([trace_payload]):
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
        if not self._send(buf):
            # Do not requeue once shutdown started: a final failed send during
            # shutdown must be counted as dropped on this first failure path so
            # shutdown() does not need a second _send() within the budget.
            if requeue_on_failure and not self._stop.is_set():
                self._requeue(buf)
            else:
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

    def _send(self, traces: list[dict[str, Any]]) -> bool:
        payload = {"traces": traces}
        headers = {"X-EvalOps-Key": self.config.api_key}
        attempt = 0
        while attempt <= self.config.max_retries:
            try:
                with httpx.Client(timeout=self.config.timeout) as client:
                    response = client.post(f"{self.config.api_url}/traces", headers=headers, json=payload)
                if 200 <= response.status_code < 300:
                    return True
                if response.status_code not in (408, 429) and response.status_code < 500:
                    return False
            except Exception:
                pass
            if attempt >= self.config.max_retries:
                return False
            sleep(self.config.retry_backoff_s * (2**attempt))
            attempt += 1
        return False
