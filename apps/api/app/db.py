"""Database engine and session factory.

G-25: this module supports SQLite (default for dev/test) and PostgreSQL
(intended for production). Selection is driven by the ``DATABASE_URL`` env var.

Supported URL forms:
  * ``sqlite:///./evalops.db`` (default) — relative paths are normalised to be
    absolute relative to ``apps/api`` so tests do not depend on CWD.
  * ``sqlite:////absolute/path.db``
  * ``postgresql+psycopg://user:pass@host:port/dbname`` — preferred prod driver.
  * ``postgresql+asyncpg://...`` — accepted but transparently rewritten to
    ``postgresql+psycopg`` since the project uses sync SQLAlchemy.
  * ``postgresql://...`` — accepted; SQLAlchemy chooses the default driver.

For Postgres deployments install the driver explicitly: ``pip install
'psycopg[binary]>=3.2'`` (already wired in ``docker-compose.prod.yml``).

Schema management (Phase 7A): production targets opt into Alembic by setting
``EVALOPS_USE_ALEMBIC=1``; the FastAPI lifespan then runs
``alembic upgrade head`` at startup. SQLite dev/test continues to use
``Base.metadata.create_all`` because the test suite recreates the database
by deleting ``evalops.db*`` between runs, which is incompatible with
Alembic's ``alembic_version`` bookkeeping. See
``docs/ops/database-migrations.md``.
"""
from collections.abc import Generator
import os

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, declarative_base, sessionmaker


def _normalize_database_url(url: str) -> str:
    if url.startswith("sqlite:///./"):
        api_root = os.path.dirname(os.path.dirname(__file__))
        rel_path = url.removeprefix("sqlite:///./")
        abs_path = os.path.abspath(os.path.join(api_root, rel_path))
        return f"sqlite:///{abs_path.replace(os.sep, '/')}"
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
    return url


DATABASE_URL = _normalize_database_url(os.getenv("DATABASE_URL", "sqlite:///./evalops.db"))

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, future=True, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
Base = declarative_base()


def is_postgres() -> bool:
    """Return True if the configured engine targets PostgreSQL."""
    return engine.dialect.name == "postgresql"


def is_sqlite() -> bool:
    return engine.dialect.name == "sqlite"


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_schema_compatibility() -> None:
    """
    Lightweight compatibility fix for local/dev databases created before
    password auth was introduced.
    """
    inspector = inspect(engine)
    if "users" not in inspector.get_table_names():
        return

    columns = {col["name"] for col in inspector.get_columns("users")}
    if "password_hash" in columns:
        return

    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE users ADD COLUMN password_hash VARCHAR(512)"))
