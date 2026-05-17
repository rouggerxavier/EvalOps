"""Structured JSON logging for EvalOps.

Scoped to `evalops.*` loggers so pytest's root-logger capture is unaffected.
Never logs: passwords, Authorization headers, JWTs, API keys, cookies, payloads.
"""
from __future__ import annotations

import json
import logging
import sys
import time

from app.request_id import get_org_id, get_request_id, get_user_id


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()
        data: dict = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "msg": message,
            "event": getattr(record, "event", message),
        }
        context_defaults = {
            "request_id": get_request_id(),
            "user_id": get_user_id(),
            "org_id": get_org_id(),
        }
        for field in (
            "request_id",
            "method",
            "path",
            "route",
            "status_code",
            "latency_ms",
            "user_id",
            "org_id",
            "error",
        ):
            val = getattr(record, field, None)
            if val is None:
                val = context_defaults.get(field)
            if val is not None:
                data[field] = val
        return json.dumps(data, ensure_ascii=False)


def configure_logging() -> None:
    logger = logging.getLogger("evalops")
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_JsonFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False


access_logger = logging.getLogger("evalops.access")
