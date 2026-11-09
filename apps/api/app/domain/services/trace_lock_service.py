"""Shared trace execution lock; held across commits until the caller finishes."""
from __future__ import annotations

import hashlib
from contextlib import contextmanager
from threading import Lock

from sqlalchemy import text
from sqlalchemy.orm import Session

_sqlite_lock = Lock()


@contextmanager
def trace_execution_lock(db: Session, trace_id: str):
    if db.get_bind().dialect.name == "postgresql":
        # Session lock survives preflight commits on the same connection: one pool slot per job.
        key = int.from_bytes(hashlib.sha256(f"sampling:{trace_id}".encode()).digest()[:8], "big", signed=True)
        engine = db.get_bind()
        with engine.connect() as connection:
            db.bind = connection
            acquired = False
            try:
                acquired = bool(connection.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": key}).scalar())
                connection.commit()
                yield acquired
            finally:
                try:
                    db.rollback()
                    if acquired:
                        connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
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
                _sqlite_lock.release()
