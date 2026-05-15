"""Alembic environment for EvalOps API.

The database URL is sourced from the same env var the app uses at runtime
(``DATABASE_URL``, with ``EVALOPS_DB_URL`` accepted as an alias). This keeps
``alembic upgrade head`` and the FastAPI lifespan pointed at the same DB
without duplicating configuration.

Supported targets:
  * SQLite (default for dev/test). Migrations use ``render_as_batch=True``
    so any ALTER TABLE-style step is rewritten by Alembic as
    copy-and-rename, which is the only safe form on SQLite.
  * PostgreSQL (prod). Native DDL is used.

Imports of the app live below ``sys.path`` setup because Alembic is invoked
from ``apps/api/`` and needs the ``app`` package importable.
"""
from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

API_ROOT = Path(__file__).resolve().parent.parent
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.db import Base, _normalize_database_url  # noqa: E402
from app import models  # noqa: F401,E402  (register models on Base.metadata)


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _resolve_url() -> str:
    url = os.getenv("DATABASE_URL") or os.getenv("EVALOPS_DB_URL")
    if not url:
        url = "sqlite:///./evalops.db"
    return _normalize_database_url(url)


config.set_main_option("sqlalchemy.url", _resolve_url())

target_metadata = Base.metadata


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=_is_sqlite(url or ""),
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = config.get_main_option("sqlalchemy.url") or ""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=_is_sqlite(url),
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
