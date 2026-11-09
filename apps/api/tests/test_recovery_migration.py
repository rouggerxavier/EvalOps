"""0014 up/down/up/check is confined to a disposable schema on dedicated PG16."""
import os
from pathlib import Path
import uuid

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url


def test_recovery_migration_roundtrip(monkeypatch):
    target = os.getenv("ACCOUNT_TEST_DATABASE_URL")
    if not target:
        pytest.skip("requires dedicated PG16")
    url = make_url(target)
    assert (url.get_backend_name(), url.host, url.port, url.database, url.username) == (
        "postgresql", "127.0.0.1", 15633, "evalops_account_test", "evalops")
    schema = "recovery_migration_" + uuid.uuid4().hex
    admin = create_engine(target)
    with admin.begin() as conn:
        assert conn.execute(text("SHOW server_version_num")).scalar().startswith("16")
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    api_root = Path(__file__).resolve().parents[1]
    # Avoid Alembic's fileConfig disabling other tests' loggers in this process.
    cfg = Config()
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    try:
        with monkeypatch.context() as patch:
            patch.setenv("DATABASE_URL", target)
            patch.setenv("PGOPTIONS", "-csearch_path=" + schema)
            command.upgrade(cfg, "head")
            engine = create_engine(target)
            with engine.begin() as conn:
                assert "password_resets" in inspect(conn).get_table_names()
                assert "credential_version" in {c["name"] for c in inspect(conn).get_columns("users")}
            engine.dispose()
            command.downgrade(cfg, "0013_user_credential_version")
            engine = create_engine(target)
            with engine.begin() as conn:
                assert "password_resets" not in inspect(conn).get_table_names()
                assert "credential_version" in {c["name"] for c in inspect(conn).get_columns("users")}
            engine.dispose()
            command.upgrade(cfg, "head")
            command.check(cfg)
    finally:
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
