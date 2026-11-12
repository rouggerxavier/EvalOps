"""0019→0020→0019→0020/check, with existing A2 and membership data retained."""
from pathlib import Path
import uuid

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from membership_helpers import pg_target


def test_existing_sqlite_organization_gets_membership_version(monkeypatch, tmp_path):
    from app import db
    engine = create_engine("sqlite:///" + str(tmp_path / "old.db"))
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE organizations (id VARCHAR(64) PRIMARY KEY, name VARCHAR(255), slug VARCHAR(255), created_at DATETIME)"))
        conn.execute(text("INSERT INTO organizations VALUES ('old', 'Old', 'old', CURRENT_TIMESTAMP)"))
    monkeypatch.setattr(db, "engine", engine)
    db.ensure_schema_compatibility()
    db.ensure_schema_compatibility()
    with engine.connect() as conn:
        assert conn.execute(text("SELECT membership_version FROM organizations WHERE id='old'")).scalar() == 0
        assert len(inspect(conn).get_columns("organizations")) == 5
    engine.dispose()


def test_invitation_migration_roundtrip(monkeypatch):
    target = pg_target()
    schema = "invitation_migration_" + uuid.uuid4().hex
    admin = create_engine(target)
    with admin.begin() as conn:
        assert conn.execute(text("SHOW server_version_num")).scalar().startswith("16")
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    cfg = Config()
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
    engine = create_engine(target, connect_args={"options": f"-csearch_path={schema}"})
    try:
        with monkeypatch.context() as patch:
            patch.setenv("DATABASE_URL", target)
            patch.setenv("PGOPTIONS", "-csearch_path=" + schema)
            command.upgrade(cfg, "0019_execution_ledger")
            with engine.begin() as conn:
                conn.execute(text("INSERT INTO organizations (id,name,slug,created_at) VALUES ('old-org','Old','old',CURRENT_TIMESTAMP)"))
                conn.execute(text("INSERT INTO users (id,email,name,credential_version,created_at) VALUES ('old-user','old@example.invalid','Old',7,CURRENT_TIMESTAMP)"))
                conn.execute(text("INSERT INTO memberships (user_id,organization_id,role,created_at) VALUES ('old-user','old-org','owner',CURRENT_TIMESTAMP)"))
                conn.execute(text("INSERT INTO password_resets (user_id,request_id,credential_version,status,requested_at,created_at,expires_at) VALUES ('old-user','old-reset',7,'pending',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"))
            command.upgrade(cfg, "head")
            with engine.begin() as conn:
                assert conn.execute(text("SELECT membership_version FROM organizations WHERE id='old-org'")).scalar() == 0
                assert conn.execute(text("SELECT role FROM memberships WHERE user_id='old-user'")).scalar() == "owner"
                assert conn.execute(text("SELECT credential_version FROM users WHERE id='old-user'")).scalar() == 7
                assert conn.execute(text("SELECT request_id FROM password_resets")).scalar() == "old-reset"
                columns = {c["name"]: c for c in inspect(conn).get_columns("organizations")}
                assert columns["membership_version"]["nullable"] is False
                assert "0" in columns["membership_version"]["default"]
                assert {"ix_organization_invitations_listing", "ix_organization_invitations_email"} <= {i["name"] for i in inspect(conn).get_indexes("organization_invitations")}
            for bad_column, bad_value in [("role", "owner"), ("status", "unknown")]:
                with pytest.raises(IntegrityError), engine.begin() as conn:
                    conn.execute(text("INSERT INTO organization_invitations (id,organization_id,email,role,status,created_at,expires_at) VALUES ('bad','old-org','bad@example.invalid',:role,:status,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"),
                                 {"role": bad_value if bad_column == "role" else "viewer", "status": bad_value if bad_column == "status" else "pending"})
            command.downgrade(cfg, "0019_execution_ledger")
            with engine.begin() as conn:
                assert "organization_invitations" not in inspect(conn).get_table_names()
                assert "membership_version" not in {c["name"] for c in inspect(conn).get_columns("organizations")}
                assert conn.execute(text("SELECT role FROM memberships")).scalar() == "owner"
                assert conn.execute(text("SELECT credential_version FROM users")).scalar() == 7
                assert conn.execute(text("SELECT request_id FROM password_resets")).scalar() == "old-reset"
            command.upgrade(cfg, "head")
            command.check(cfg)
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
