"""Fase A — worker infra smoke tests.

Validates that `WorkerSettings` imports cleanly with arq installed, exposes the
required attributes, and that `worker_concurrency()` honours the env override.
"""
from __future__ import annotations

import importlib
import os


def test_worker_settings_loads_with_empty_function_list() -> None:
    from app.workers.settings import WorkerSettings

    assert WorkerSettings.functions == []
    assert callable(WorkerSettings.on_startup)
    assert callable(WorkerSettings.on_shutdown)
    assert WorkerSettings.max_jobs >= 1


def test_worker_concurrency_env_override(monkeypatch) -> None:
    from app import config

    monkeypatch.setenv("EVALOPS_WORKER_CONCURRENCY", "7")
    assert config.worker_concurrency() == 7
    monkeypatch.delenv("EVALOPS_WORKER_CONCURRENCY", raising=False)
    assert config.worker_concurrency() == 4


def test_worker_settings_redis_settings_uses_url(monkeypatch) -> None:
    monkeypatch.setenv("REDIS_URL", "redis://example.invalid:6380/2")
    import app.workers.settings as settings_module

    importlib.reload(settings_module)
    rs = settings_module.WorkerSettings.redis_settings
    assert rs.host == "example.invalid"
    assert rs.port == 6380
    assert rs.database == 2
    monkeypatch.delenv("REDIS_URL", raising=False)
    importlib.reload(settings_module)
