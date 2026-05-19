"""Phase 7F-C — cleanup service tests.

Covers (spec §11 cleanup matrix + user disposition for 7F-C):

RevokedToken: dry-run mutates nothing; expired deleted; future preserved;
idempotent; inclusive ``expires_at == now`` boundary; ``limit`` honoured;
naive datetimes tolerated.

ExportJob: dry-run mutates nothing; expired+safe file → file+row removed;
future preserved; ``expires_at IS NULL`` skipped; missing file → row removed
without error; path traversal / symlink → ``skipped_unsafe`` + row preserved
+ nothing deleted outside the base dir; ``delete_files=False`` preserves
file+row; idempotent; boundary; ``audit_logs`` never touched; summary leaks
no path/secret.

No Redis, no rate limiter, no scheduler, no network — SQLite + tmp dirs only.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.db import Base, SessionLocal, engine
from app.maintenance.cleanup import (
    CleanupSummary,
    cleanup_expired_export_jobs,
    cleanup_expired_revoked_tokens,
)
from app.models import AuditLog, ExportJob, RevokedToken


def _utc(offset_seconds: int = 0) -> datetime:
    return datetime.now(timezone.utc) + timedelta(seconds=offset_seconds)


# ── RevokedToken ─────────────────────────────────────────────────────────────


def _add_revoked(jti: str, expires_at: datetime) -> None:
    with SessionLocal() as db:
        db.add(RevokedToken(jti=jti, expires_at=expires_at, revoked_at=_utc(-3600)))
        db.commit()


def test_revoked_dry_run_mutates_nothing() -> None:
    _add_revoked("jti_exp", _utc(-3600))
    with SessionLocal() as db:
        summary = cleanup_expired_revoked_tokens(db, dry_run=True)
    assert summary.dry_run is True
    assert summary.deleted_rows == 1
    with SessionLocal() as db:
        assert db.get(RevokedToken, "jti_exp") is not None


def test_revoked_expired_deleted_future_preserved() -> None:
    _add_revoked("jti_old", _utc(-10))
    _add_revoked("jti_future", _utc(3600))
    with SessionLocal() as db:
        summary = cleanup_expired_revoked_tokens(db, dry_run=False)
    assert summary.deleted_rows == 1
    with SessionLocal() as db:
        assert db.get(RevokedToken, "jti_old") is None
        assert db.get(RevokedToken, "jti_future") is not None


def test_revoked_idempotent_second_run_zero() -> None:
    _add_revoked("jti_old", _utc(-10))
    with SessionLocal() as db:
        cleanup_expired_revoked_tokens(db, dry_run=False)
    with SessionLocal() as db:
        again = cleanup_expired_revoked_tokens(db, dry_run=False)
    assert again.deleted_rows == 0


def test_revoked_boundary_equal_now_is_expired() -> None:
    now = _utc(0)
    _add_revoked("jti_boundary", now)
    with SessionLocal() as db:
        summary = cleanup_expired_revoked_tokens(db, now=now, dry_run=False)
    assert summary.deleted_rows == 1
    with SessionLocal() as db:
        assert db.get(RevokedToken, "jti_boundary") is None


def test_revoked_limit_respected() -> None:
    for i in range(5):
        _add_revoked(f"jti_{i}", _utc(-1000 + i))
    with SessionLocal() as db:
        summary = cleanup_expired_revoked_tokens(db, dry_run=False, limit=2)
    assert summary.scanned == 2
    assert summary.deleted_rows == 2
    with SessionLocal() as db:
        assert db.query(RevokedToken).count() == 3


def test_revoked_naive_datetime_tolerated() -> None:
    # SQLite can hand back naive datetimes; cleanup must not raise.
    _add_revoked("jti_naive", datetime.utcnow() - timedelta(hours=1))  # noqa: DTZ003
    with SessionLocal() as db:
        summary = cleanup_expired_revoked_tokens(db, dry_run=False)
    assert summary.deleted_rows == 1


# ── ExportJob ────────────────────────────────────────────────────────────────


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


def _write_export_file(base, job_id: str) -> "object":
    f = base / f"{job_id}.jsonl"
    f.write_text('{"row": 1}\n', encoding="utf-8")
    return f


def test_export_dry_run_mutates_nothing(tmp_path) -> None:
    _add_export("expj_dry", _utc(-3600))
    f = _write_export_file(tmp_path, "expj_dry")
    with SessionLocal() as db:
        summary = cleanup_expired_export_jobs(
            db, dry_run=True, exports_base=tmp_path
        )
    assert summary.dry_run is True
    assert summary.deleted_rows == 1
    assert f.exists()
    with SessionLocal() as db:
        assert db.get(ExportJob, "expj_dry") is not None


def test_export_expired_safe_file_and_row_removed(tmp_path) -> None:
    _add_export("expj_old", _utc(-10))
    f = _write_export_file(tmp_path, "expj_old")
    with SessionLocal() as db:
        summary = cleanup_expired_export_jobs(
            db, dry_run=False, exports_base=tmp_path
        )
    assert summary.deleted_files == 1
    assert summary.deleted_rows == 1
    assert not f.exists()
    with SessionLocal() as db:
        assert db.get(ExportJob, "expj_old") is None


def test_export_future_preserved(tmp_path) -> None:
    _add_export("expj_future", _utc(3600))
    f = _write_export_file(tmp_path, "expj_future")
    with SessionLocal() as db:
        summary = cleanup_expired_export_jobs(
            db, dry_run=False, exports_base=tmp_path
        )
    assert summary.deleted_rows == 0
    assert f.exists()
    with SessionLocal() as db:
        assert db.get(ExportJob, "expj_future") is not None


def test_export_null_expiry_skipped(tmp_path) -> None:
    _add_export("expj_null", None)
    with SessionLocal() as db:
        summary = cleanup_expired_export_jobs(
            db, dry_run=False, exports_base=tmp_path
        )
    assert summary.scanned == 0
    assert summary.deleted_rows == 0
    with SessionLocal() as db:
        assert db.get(ExportJob, "expj_null") is not None


def test_export_missing_file_row_removed_no_error(tmp_path) -> None:
    _add_export("expj_nofile", _utc(-10))  # no file written
    with SessionLocal() as db:
        summary = cleanup_expired_export_jobs(
            db, dry_run=False, exports_base=tmp_path
        )
    assert summary.missing_files == 1
    assert summary.deleted_rows == 1
    assert summary.errors == 0
    with SessionLocal() as db:
        assert db.get(ExportJob, "expj_nofile") is None


def test_export_path_traversal_skipped_and_row_preserved(tmp_path) -> None:
    base = tmp_path / "exports"
    base.mkdir()
    outside = tmp_path / "outside.jsonl"
    outside.write_text("SENSITIVE\n", encoding="utf-8")
    # job id crafted to escape base via the reconstructed path.
    _add_export("../outside", _utc(-10))
    with SessionLocal() as db:
        summary = cleanup_expired_export_jobs(
            db, dry_run=False, exports_base=base
        )
    assert summary.skipped_unsafe == 1
    assert summary.deleted_rows == 0
    assert outside.exists()  # nothing deleted outside the base dir
    assert outside.read_text(encoding="utf-8") == "SENSITIVE\n"
    with SessionLocal() as db:
        assert db.get(ExportJob, "../outside") is not None


def test_export_symlink_not_followed_and_row_preserved(tmp_path) -> None:
    base = tmp_path / "exports"
    base.mkdir()
    target = tmp_path / "real_secret.jsonl"
    target.write_text("SECRET\n", encoding="utf-8")
    link = base / "expj_link.jsonl"
    link.symlink_to(target)
    _add_export("expj_link", _utc(-10))
    with SessionLocal() as db:
        summary = cleanup_expired_export_jobs(
            db, dry_run=False, exports_base=base
        )
    assert summary.skipped_unsafe == 1
    assert summary.deleted_rows == 0
    assert target.exists()  # symlink target untouched
    assert target.read_text(encoding="utf-8") == "SECRET\n"
    with SessionLocal() as db:
        assert db.get(ExportJob, "expj_link") is not None


def test_export_delete_files_false_preserves_file_and_row(tmp_path) -> None:
    _add_export("expj_keep", _utc(-10))
    f = _write_export_file(tmp_path, "expj_keep")
    with SessionLocal() as db:
        summary = cleanup_expired_export_jobs(
            db, dry_run=False, delete_files=False, exports_base=tmp_path
        )
    assert summary.deleted_rows == 0
    assert f.exists()
    with SessionLocal() as db:
        assert db.get(ExportJob, "expj_keep") is not None


def test_export_idempotent_second_run_zero(tmp_path) -> None:
    _add_export("expj_idem", _utc(-10))
    _write_export_file(tmp_path, "expj_idem")
    with SessionLocal() as db:
        cleanup_expired_export_jobs(db, dry_run=False, exports_base=tmp_path)
    with SessionLocal() as db:
        again = cleanup_expired_export_jobs(
            db, dry_run=False, exports_base=tmp_path
        )
    assert again.deleted_rows == 0
    assert again.scanned == 0


def test_export_boundary_equal_now_is_expired(tmp_path) -> None:
    now = _utc(0)
    _add_export("expj_boundary", now)
    _write_export_file(tmp_path, "expj_boundary")
    with SessionLocal() as db:
        summary = cleanup_expired_export_jobs(
            db, now=now, dry_run=False, exports_base=tmp_path
        )
    assert summary.deleted_rows == 1
    with SessionLocal() as db:
        assert db.get(ExportJob, "expj_boundary") is None


def test_audit_logs_untouched_by_cleanup(tmp_path) -> None:
    with SessionLocal() as db:
        db.add(
            AuditLog(
                id="aud_keep",
                organization_id=None,
                action="export.created",
                target_type="project",
                target_id="proj_test",
                payload={"export_id": "expj_old"},
            )
        )
        db.commit()
    _add_export("expj_old", _utc(-10))
    _write_export_file(tmp_path, "expj_old")
    with SessionLocal() as db:
        cleanup_expired_export_jobs(db, dry_run=False, exports_base=tmp_path)
        cleanup_expired_revoked_tokens(db, dry_run=False)
    with SessionLocal() as db:
        assert db.get(AuditLog, "aud_keep") is not None


def test_summary_is_secret_free_and_serialisable() -> None:
    summary = CleanupSummary(target="export_jobs", unsafe_ids=["expj_x"])
    d = summary.as_dict()
    # Only counts + opaque ids; no path/jti keys, JSON-safe.
    assert set(d) == {
        "target", "scanned", "deleted_rows", "deleted_files",
        "missing_files", "skipped_unsafe", "dry_run", "errors", "unsafe_ids",
    }
    import json

    json.dumps(d)
