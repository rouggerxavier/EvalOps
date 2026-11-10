"""Additive migration preserves legacy decisions and supports a real round trip."""
from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

import pytest
from sqlalchemy import MetaData, create_engine, select, text
from sqlalchemy.engine import make_url

API_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("dialect", ["sqlite", "postgresql"])
def test_task_migration_preserves_legacy(dialect, tmp_path):
    target = f"sqlite:///{tmp_path / 'migration.db'}"
    schema = None
    admin = None
    options = {}
    if dialect == "postgresql":
        target = os.environ.get("EVALOPS_OFFLINE_TEST_DATABASE_URL")
        if not target:
            pytest.skip("dedicated PostgreSQL target not configured")
        parsed = make_url(target)
        assert parsed.host == "127.0.0.1" and parsed.port == 15636 and parsed.database == "offline_test"
        admin = create_engine(target)
        schema = "migration_" + uuid4().hex
        with admin.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        options = {"options": f"-csearch_path={schema}"}
    engine = create_engine(target, connect_args=options)
    env = {**os.environ, "DATABASE_URL": target}
    if schema:
        env["PGOPTIONS"] = f"-csearch_path={schema}"
    def alembic(*args):
        result = subprocess.run([sys.executable, "-m", "alembic", *args], cwd=API_ROOT,
                                env=env, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
    try:
        alembic("upgrade", "0013_user_credential_version")
        metadata = MetaData()
        metadata.reflect(engine)
        now = datetime.now(timezone.utc)
        data = {
            "organizations": {"id": "org", "name": "Org", "slug": "org", "created_at": now},
            "projects": {"id": "p", "organization_id": "org", "name": "Project", "slug": "p", "default_environment": "dev", "created_at": now},
            "datasets": {"id": "d", "project_id": "p", "slug": "data", "source": "manual", "created_at": now},
            "rubrics": {"id": "r", "project_id": "p", "slug": "rubric", "current_version": 1, "threshold": 0.7, "created_at": now},
            "experiments": {"id": "e", "project_id": "p", "name": "Legacy", "dataset_id": "d", "rubric_id": "r", "variants": [], "pass_criteria": {}, "created_at": now},
            "experiment_runs": {"id": "run", "experiment_id": "e", "project_id": "p", "status": "error", "triggered_by": "api", "passed": False,
                "by_variant": {"legacy": {"score": 0.25}}, "comparisons": {"raw": None}, "criteria_failures": ["technical_error"], "run_metadata": {"old": True}, "created_at": now},
        }
        with engine.begin() as conn:
            for table, values in data.items():
                conn.execute(metadata.tables[table].insert().values(**values))
        def legacy_values():
            with engine.connect() as conn:
                row = conn.execute(select(metadata.tables["experiment_runs"])).mappings().one()
                return {key: row[key] for key in data["experiment_runs"]}
        expected = legacy_values()
        alembic("upgrade", "head")
        assert legacy_values() == expected
        with engine.connect() as conn:
            row = conn.execute(text("SELECT kind, decision, decision_reasons FROM experiment_runs")).one()
            assert row.kind == "legacy_synthetic" and row.decision is None
        alembic("downgrade", "0013_user_credential_version")
        assert legacy_values() == expected
        alembic("upgrade", "head")
        assert legacy_values() == expected
        if dialect == "postgresql":
            alembic("check")
    finally:
        engine.dispose()
        if schema:
            with admin.begin() as conn:
                conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            admin.dispose()
