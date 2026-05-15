"""Test isolation for SQLite (Fix-7B.3 / audit A-09).

Problem
-------
``app.db`` builds a *module-level* engine bound to a single shared
``evalops.db`` file with SQLAlchemy's default ``QueuePool``. Every test
imports ``app.main`` and therefore shares that engine. The per-file
``Base.metadata.drop_all`` / ``create_all`` fixtures then race against
connections still parked in the pool (and TestClient worker threads),
producing intermittent ``sqlite3.OperationalError: database is locked``.
The historical workaround was ``rm -f evalops.db*`` plus running tests in
small groups.

Fix
---
This top-level ``conftest.py`` is imported by pytest *before* any test
module (and before ``app.main`` / the service layer bind the names
``engine`` / ``SessionLocal`` via ``from app.db import ...``). It rebinds
``app.db`` to a per-run temporary SQLite file using ``NullPool`` so no
connection is ever held open in a pool. With no parked connections,
``drop_all``/``create_all`` always acquire the exclusive lock, and the
database file lives in an OS temp dir that is unique per test run — so
``rm -f evalops.db*`` is no longer required and tests cannot inherit
residual state from a previous run.

This is test-only wiring: production ``app.db`` behaviour is unchanged.
"""
from __future__ import annotations

import os
import shutil
import tempfile

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

# Import the module object (not its names) so the rebind below is visible
# to every later ``from app.db import engine/SessionLocal`` / ``get_db``.
import app.db as _db

_TMP_DIR = tempfile.mkdtemp(prefix="evalops-test-")
_DB_PATH = os.path.join(_TMP_DIR, "test.db")
_TEST_DATABASE_URL = f"sqlite:///{_DB_PATH.replace(os.sep, '/')}"

# NullPool: every connection is closed and discarded on return instead of
# being parked in a pool, so a subsequent drop_all/create_all can take the
# SQLite exclusive lock without contending with a stale pooled connection.
_test_engine = create_engine(
    _TEST_DATABASE_URL,
    future=True,
    poolclass=NullPool,
    connect_args={"check_same_thread": False},
)
_TestSessionLocal = sessionmaker(
    bind=_test_engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)

# Rebind BEFORE app.main / services import these names. ``get_db`` looks up
# ``SessionLocal`` on the module at call time, so rebinding the attribute is
# enough for the FastAPI dependency path too.
_db.DATABASE_URL = _TEST_DATABASE_URL
_db.engine = _test_engine
_db.SessionLocal = _TestSessionLocal

# Now safe to import: app.main does ``from app.db import ... engine,
# SessionLocal`` and picks up the rebound objects above.
from app.db import Base  # noqa: E402
from app.main import app as _app  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_sqlite_schema():
    """Guarantee a clean schema per test and never leak a TestClient
    dependency override into the next test.

    Existing per-file fixtures keep their own drop_all/create_all (they now
    operate on the rebound NullPool engine); this fixture is the common
    safety net for files that have none (e.g. test_health) and the single
    place that clears ``app.dependency_overrides``.
    """
    Base.metadata.create_all(bind=_test_engine)
    # Snapshot, not clear(): some suites (e.g. test_phase11) install a
    # module-scoped get_db override that must survive across the function
    # tests in that module. Restoring the snapshot still drops any
    # per-test override while preserving wider-scoped ones.
    saved_overrides = dict(_app.dependency_overrides)
    yield
    _app.dependency_overrides.clear()
    _app.dependency_overrides.update(saved_overrides)
    Base.metadata.drop_all(bind=_test_engine)
    _test_engine.dispose()


def pytest_sessionfinish(session, exitstatus):  # noqa: ARG001
    """Remove the per-run temp database directory."""
    shutil.rmtree(_TMP_DIR, ignore_errors=True)
