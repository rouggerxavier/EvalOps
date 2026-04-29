from __future__ import annotations

from dataclasses import dataclass
from queue import Empty, Full, Queue
from threading import Event, Thread
from time import monotonic
from typing import Any

import httpx


@dataclass
class UploaderConfig:
    api_url: str
    api_key: str
    max_queue: int = 1024
    flush_interval: float = 2.0
    max_batch: int = 64
    timeout: float = 5.0


class BackgroundUploader:
    def __init__(self, config: UploaderConfig) -> None:
        self.config = config
        self.queue: Queue[dict[str, Any]] = Queue(maxsize=config.max_queue)
        self._stop = Event()
        self._thread = Thread(target=self._loop, daemon=True)
        self._thread.start()

    def submit(self, trace_payload: dict[str, Any]) -> None:
        try:
            self.queue.put_nowait(trace_payload)
        except Full:
            return

    def flush(self) -> None:
        self._send_buffered(force=True)

    def shutdown(self) -> None:
        self._stop.set()
        self._thread.join(timeout=1)
        self._send_buffered(force=True)

    def _send_buffered(self, force: bool = False) -> None:
        buf: list[dict[str, Any]] = []
        while len(buf) < self.config.max_batch:
            try:
                buf.append(self.queue.get_nowait())
            except Empty:
                break
        if not buf and not force:
            return
        if buf:
            self._send(buf)

    def _loop(self) -> None:
        buf: list[dict[str, Any]] = []
        last_flush = monotonic()
        while not self._stop.is_set():
            timeout = max(0.0, self.config.flush_interval - (monotonic() - last_flush))
            try:
                item = self.queue.get(timeout=timeout)
                buf.append(item)
            except Empty:
                pass
            if buf and (len(buf) >= self.config.max_batch or monotonic() - last_flush >= self.config.flush_interval):
                self._send(buf)
                buf.clear()
                last_flush = monotonic()
        if buf:
            self._send(buf)

    def _send(self, traces: list[dict[str, Any]]) -> None:
        payload = {"traces": traces}
        headers = {"X-EvalOps-Key": self.config.api_key}
        try:
            with httpx.Client(timeout=self.config.timeout) as client:
                client.post(f"{self.config.api_url}/traces", headers=headers, json=payload)
        except Exception:
            return
