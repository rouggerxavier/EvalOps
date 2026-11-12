"""Shared trace execution lock; held across commits until the caller finishes."""
from __future__ import annotations

import hashlib
from contextlib import contextmanager
from threading import Lock

from sqlalchemy import text
from sqlalchemy.orm import Session

_sqlite_lock = Lock()


@contextmanager
def trace_execution_lock(db: Session, trace_id: str | list[str] | tuple[str, ...]):
    trace_ids = sorted(set([trace_id] if isinstance(trace_id, str) else trace_id))
    if db.get_bind().dialect.name == "postgresql":
        # Session lock survives preflight commits on the same connection: one pool slot per job.
        keys = [int.from_bytes(hashlib.sha256(f"sampling:{item}".encode()).digest()[:8], "big", signed=True)
                for item in trace_ids]
        engine = db.get_bind()
        with engine.connect() as connection:
            db.bind = connection
            acquired_keys = []
            try:
                for key in keys:
                    if not connection.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": key}).scalar():
                        break
                    acquired_keys.append(key)
                connection.commit()
                yield len(acquired_keys) == len(keys)
            finally:
                try:
                    db.rollback()
                    for key in reversed(acquired_keys):
                        connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
                    if acquired_keys:
                        connection.commit()
                except BaseException:
                    connection.invalidate()
                    raise
                finally:
                    db.bind = engine
    else:
        # shortcut: SQLite workers serialize within one process; use Postgres for multiple workers.
        acquired = _sqlite_lock.acquire(blocking=False)
        try:
            yield acquired
        finally:
            if acquired:
                try:
                    db.rollback()
                finally:
                    _sqlite_lock.release()
