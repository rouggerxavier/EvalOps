"""Phase 7F-D — operational cleanup CLI contract tests.

These tests cover the `python -m app.maintenance.cleanup` entrypoint surface:
dry-run default, explicit apply, target selection, per-target limit, stable
JSON output, human summary output, exit codes, and secret/path hygiene.
"""
from __future__ import annotations

import json
import logging
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.db import SessionLocal
from app.maintenance import cleanup
from app.models import ExportJob, RevokedToken


def _utc(offset_seconds: int = 0) -> datetime:
    return datetime.now(timezone.utc) + timedelta(seconds=offset_seconds)


def _add_revoked(jti: str, expires_at: datetime) -> None:
    with SessionLocal() as db:
        db.add(RevokedToken(jti=jti, expires_at=expires_at, revoked_at=_utc(-3600)))
        db.commit()


def _add_export(job_id: str, expires_at: datetime | None) -> None:
    with SessionLocal() as db:
        db.add(
            ExportJob(
                id=job_id,
                project_id="proj_test",
                status="completed",
                format="jsonl",
                expires_at=expires_at,
            )
        )
        db.commit()


def _write_export_file(base: Path, job_id: str) -> Path:
    path = base / f"{job_id}.jsonl"
    path.write_text('{"row": 1}\n', encoding="utf-8")
    return path


def _payload(capsys: pytest.CaptureFixture[str]) -> dict:
    out = capsys.readouterr().out
    return json.loads(out)


def test_cli_default_is_dry_run_json_and_mutates_nothing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("EVALOPS_EXPORTS_DIR", str(tmp_path))
    _add_revoked("sensitive-jti", _utc(-60))
    _add_export("expj_dry_cli", _utc(-60))
    export_file = _write_export_file(tmp_path, "expj_dry_cli")

    assert cleanup.main(["--json"]) == 0
    payload = _payload(capsys)

    assert payload["ok"] is True
    assert payload["dry_run"] is True
    assert payload["target"] == "all"
    assert payload["totals"]["deleted_rows"] == 2
    assert payload["totals"]["deleted_files"] == 1
    assert export_file.exists()
    with SessionLocal() as db:
        assert db.get(RevokedToken, "sensitive-jti") is not None
        assert db.get(ExportJob, "expj_dry_cli") is not None

    serialized = json.dumps(payload)
    assert "sensitive-jti" not in serialized
    assert str(tmp_path) not in serialized


def test_cli_apply_deletes_selected_exports_only(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("EVALOPS_EXPORTS_DIR", str(tmp_path))
    _add_revoked("jti_keep_cli", _utc(-60))
    _add_export("expj_apply_cli", _utc(-60))
    export_file = _write_export_file(tmp_path, "expj_apply_cli")

    assert cleanup.main(["--apply", "--target", "exports", "--json"]) == 0
    payload = _payload(capsys)

    assert payload["dry_run"] is False
    assert payload["target"] == "exports"
    assert [s["target"] for s in payload["summaries"]] == ["export_jobs"]
    assert payload["totals"]["deleted_rows"] == 1
    assert payload["totals"]["deleted_files"] == 1
    assert not export_file.exists()
    with SessionLocal() as db:
        assert db.get(ExportJob, "expj_apply_cli") is None
        assert db.get(RevokedToken, "jti_keep_cli") is not None


def test_cli_target_revoked_tokens_and_limit(
    capsys: pytest.CaptureFixture[str],
) -> None:
    for i in range(3):
        _add_revoked(f"jti_limit_{i}", _utc(-300 + i))

    assert cleanup.main(
        ["--apply", "--target", "revoked-tokens", "--limit", "2", "--json"]
    ) == 0
    payload = _payload(capsys)

    assert payload["target"] == "revoked-tokens"
    assert payload["limit"] == 2
    assert payload["totals"]["scanned"] == 2
    assert payload["totals"]["deleted_rows"] == 2
    with SessionLocal() as db:
        assert db.query(RevokedToken).count() == 1


def test_cli_human_summary_is_stable(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _add_revoked("jti_human", _utc(-60))

    assert cleanup.main(["--target", "revoked-tokens"]) == 0
    out = capsys.readouterr().out

    assert "status=ok mode=dry-run target=revoked-tokens limit=none" in out
    assert "target=revoked_tokens" in out
    assert "total scanned=1 deleted_rows=1" in out


def test_cli_returns_nonzero_when_cleanup_reports_errors(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    summary = cleanup.CleanupSummary(target="export_jobs", errors=1, dry_run=False)
    monkeypatch.setattr(cleanup, "run_target", lambda *args, **kwargs: [summary])

    assert cleanup.main(["--apply", "--target", "exports", "--json"]) == 1
    payload = _payload(capsys)
    assert payload["ok"] is False
    assert payload["totals"]["errors"] == 1


def test_cli_returns_sanitized_nonzero_on_unhandled_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret_path = tmp_path / "secret.db"

    def _boom(*args, **kwargs):
        raise RuntimeError(f"database failed at {secret_path}")

    monkeypatch.setattr(cleanup, "run_target", _boom)

    caplog.set_level(logging.ERROR, logger="evalops.maintenance")
    assert cleanup.main(["--json"]) == 1
    captured = capsys.readouterr()
    payload = json.loads(captured.err)
    assert payload["ok"] is False
    assert payload["error"] == "cleanup_failed"
    assert str(secret_path) not in captured.err
    assert str(secret_path) not in caplog.text
    assert captured.out == ""


def test_cli_rejects_non_positive_limit() -> None:
    with pytest.raises(SystemExit) as exc:
        cleanup.main(["--limit", "0"])
    assert exc.value.code == 2


def test_python_module_help_entrypoint_works() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "app.maintenance.cleanup", "--help"],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "--target" in result.stdout
    assert "--limit" in result.stdout
    assert "--json" in result.stdout
