"""0021→0022→0021→0022/check preserves A2, memberships and runner evidence."""
from datetime import datetime, timezone
from pathlib import Path
import uuid

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import MetaData, create_engine, inspect, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

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


@pytest.mark.parametrize("dialect", ["sqlite", "postgresql"])
def test_invitation_migration_roundtrip(monkeypatch, tmp_path, dialect):
    target, schema, admin = "sqlite:///" + str(tmp_path / "invitation.db"), None, None
    if dialect == "postgresql":
        target = pg_target()
        schema = "invitation_migration_" + uuid.uuid4().hex
        admin = create_engine(target)
        with admin.begin() as conn:
            assert conn.execute(text("SHOW server_version_num")).scalar().startswith("16")
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    cfg = Config()
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
    engine = create_engine(target, connect_args={"options": f"-csearch_path={schema}"} if schema else {})
    try:
        with monkeypatch.context() as patch:
            patch.setenv("DATABASE_URL", target)
            if schema:
                patch.setenv("PGOPTIONS", "-csearch_path=" + schema)
            command.upgrade(cfg, "0021_runner_leases")
            with engine.begin() as conn:
                conn.execute(text("INSERT INTO organizations (id,name,slug,created_at) VALUES ('old-org','Old','old',CURRENT_TIMESTAMP)"))
                conn.execute(text("INSERT INTO users (id,email,name,credential_version,created_at) VALUES ('old-user','old@example.invalid','Old',7,CURRENT_TIMESTAMP)"))
                conn.execute(text("INSERT INTO memberships (user_id,organization_id,role,created_at) VALUES ('old-user','old-org','owner',CURRENT_TIMESTAMP)"))
                conn.execute(text("INSERT INTO password_resets (user_id,request_id,credential_version,status,requested_at,created_at,expires_at) VALUES ('old-user','old-reset',7,'pending',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"))
            metadata = MetaData()
            metadata.reflect(engine)
            now = datetime.now(timezone.utc)
            rows = {
                "projects": {"id": "old-project", "organization_id": "old-org", "name": "Old", "slug": "old", "default_environment": "dev", "created_at": now},
                "runners": {"id": "old-runner", "project_id": "old-project", "name": "Old", "owner_user_id": "old-user", "capabilities": {}, "access_label": {}, "created_at": now},
                "executions": {"id": "old-execution", "project_id": "old-project", "environment": "dev", "origin": "controlled_runner", "mode": "application_adapter", "status": "uncertain",
                               "manifest_hash": "sha256:" + "1" * 64, "manifest_content": "{}", "access_label": {}, "created_by": "old-user", "created_at": now},
                "runner_credentials": {"id": "old-key", "runner_id": "old-runner", "project_id": "old-project", "prefix": "evk", "hash": "hash", "expires_at": now, "created_at": now},
                "execution_leases": {"execution_id": "old-execution", "project_id": "old-project", "attempt_id": "old-attempt", "runner_id": "old-runner", "credential_id": "old-key", "claim_key": "old-claim",
                                     "token_hash": "sha256:" + "2" * 64, "state": "expired", "claimed_at": now, "expires_at": now, "ended_at": now},
                "execution_late_reports": {"id": "old-report", "execution_id": "old-execution", "project_id": "old-project", "attempt_id": "old-attempt", "reason": "lease_closed", "content": "{}", "content_hash": "sha256:" + "3" * 64, "created_at": now},
                "execution_ledger_entries": {"id": "old-ledger", "execution_id": "old-execution", "project_id": "old-project", "organization_id": "old-org", "attempt_id": "old-attempt", "period": "2026-11", "kind": "reserve", "event_key": "reserve",
                                             "amount_units": 100000000, "measurement_source": "fixture", "pricing_version": "fixture@1", "actor_id": "old-user", "created_at": now},
            }
            with engine.begin() as conn:
                for table, values in rows.items():
                    conn.execute(metadata.tables[table].insert().values(**values))

            def evidence():
                with engine.connect() as conn:
                    return [tuple(conn.execute(select(metadata.tables[table])).one()) for table in rows]

            expected_evidence = evidence()
            command.upgrade(cfg, "0022_organization_invitations")
            assert evidence() == expected_evidence
            with engine.begin() as conn:
                assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == "0022_organization_invitations"
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
            for table in ("execution_leases", "execution_late_reports", "execution_ledger_entries"):
                with pytest.raises(DBAPIError, match="immutable_task_resource"), engine.begin() as conn:
                    conn.execute(text(f"DELETE FROM {table}"))
            command.downgrade(cfg, "0021_runner_leases")
            assert evidence() == expected_evidence
            with engine.begin() as conn:
                assert "organization_invitations" not in inspect(conn).get_table_names()
                assert "membership_version" not in {c["name"] for c in inspect(conn).get_columns("organizations")}
                assert conn.execute(text("SELECT role FROM memberships")).scalar() == "owner"
                assert conn.execute(text("SELECT credential_version FROM users")).scalar() == 7
                assert conn.execute(text("SELECT request_id FROM password_resets")).scalar() == "old-reset"
            # The invitation assertions target 0022; schema check must run at the latest head.
            command.upgrade(cfg, "head")
            assert evidence() == expected_evidence
            if dialect == "postgresql":
                # SQLite cannot compare legacy expression indexes/defaults faithfully; its assertions above check this migration directly.
                command.check(cfg)
    finally:
        engine.dispose()
        if admin:
            with admin.begin() as conn:
                conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            admin.dispose()
