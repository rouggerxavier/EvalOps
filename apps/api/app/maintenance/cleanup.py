"""Phase 7F-C — idempotent cleanup services for expired retention rows.

Two targets, both gap items from the Phase 7F spec
(``docs/plans/evalops-phase7f-redis-cleanup-spec.md`` §6):

* ``RevokedToken``  — JWT denylist rows are redundant once ``expires_at``
  passes (the underlying JWT is already rejected by ``decode_access_token``),
  so expired rows are hard-deleted (spec decision #6).
* ``ExportJob``     — expired jobs already return 410 on download; the row
  has no remaining product value. The model has no cleanup-marker column and
  this phase adds **no migration**, so the expired row is hard-deleted after
  its on-disk ``<job.id>.jsonl`` file is removed *only when path-safe*
  (spec decision #5; user disposition for 7F-C).

Design constraints (spec §6, Option A):

* idempotent  — a second run over the same data deletes nothing and never
  raises; a missing export file is success, not an error.
* dry-run     — ``dry_run=True`` performs only the SELECT, mutates no row,
  unlinks no file, returns accurate counts.
* path-safe   — never follow a symlink, never escape ``exports_dir()``,
  never delete a directory; an unsafe path leaves the row in place so the
  operational problem stays visible.
* no scheduler — plain functions plus a thin ``python -m`` shell. External
  cron / platform scheduler is the deploy-time invocation surface (7F-D).
* safe logs   — counts and opaque job ids only; never the raw ``jti`` nor
  absolute filesystem paths.

Boundary policy: ``expires_at <= now`` is treated as expired (inclusive),
matching ``app.deps._is_expired``. ``expires_at IS NULL`` means "no expiry"
and is always skipped.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import exports_dir
from app.models import ExportJob, PasswordReset, RevokedToken

logger = logging.getLogger("evalops.maintenance")

TARGET_ALL = "all"
TARGET_REVOKED_TOKENS = "revoked-tokens"
TARGET_EXPORTS = "exports"
TARGET_PASSWORD_RESETS = "password-resets"
TARGET_CHOICES = (TARGET_ALL, TARGET_REVOKED_TOKENS, TARGET_EXPORTS, TARGET_PASSWORD_RESETS)


def _now(now: datetime | None) -> datetime:
    return now if now is not None else datetime.now(timezone.utc)


def _is_expired(expires_at: datetime | None, now: datetime) -> bool:
    """Inclusive expiry check, naive/aware tolerant.

    Mirrors ``app.deps._is_expired``: SQLite returns naive datetimes, so
    drop the tzinfo on ``now`` when the stored value is naive before the
    ``<=`` comparison (boundary ``expires_at == now`` counts as expired).
    """
    if expires_at is None:
        return False
    if expires_at.tzinfo is None or expires_at.utcoffset() is None:
        now = now.replace(tzinfo=None)
    else:
        now = now.astimezone(expires_at.tzinfo)
    return expires_at <= now


def _is_within(base: Path, candidate: Path) -> bool:
    """True iff resolved ``candidate`` is inside resolved ``base``.

    ``Path.is_relative_to`` exists on 3.9+; keep an explicit fallback so the
    safety check never depends on the interpreter minor version.
    """
    try:
        candidate.relative_to(base)
        return True
    except ValueError:
        return False


@dataclass
class CleanupSummary:
    """Structured, secret-free result of a single cleanup run.

    Carries counts and a bounded list of opaque ids only — no paths, no
    ``jti`` values, no row payloads. Safe to log and to assert on in tests.
    """

    target: str
    scanned: int = 0
    deleted_rows: int = 0
    deleted_files: int = 0
    missing_files: int = 0
    skipped_unsafe: int = 0
    dry_run: bool = True
    errors: int = 0
    unsafe_ids: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


def cleanup_expired_revoked_tokens(
    session: Session,
    *,
    now: datetime | None = None,
    dry_run: bool = True,
    limit: int | None = None,
) -> CleanupSummary:
    """Delete ``RevokedToken`` rows whose ``expires_at <= now``.

    Safe because once ``expires_at`` passes the JWT is independently expired
    and rejected by ``decode_access_token``; the denylist row is redundant.
    Rows with a future ``expires_at`` are preserved. Idempotent: a second
    run finds nothing and deletes nothing.

    ``dry_run=True`` (default) returns the count without touching the DB.
    ``limit`` bounds a single run (oldest-expiring first) for batching.
    Never logs the ``jti`` (treated as sensitive); counts only.
    """
    moment = _now(now)
    summary = CleanupSummary(target="revoked_tokens", dry_run=dry_run)

    query = session.query(RevokedToken).order_by(RevokedToken.expires_at.asc())
    if limit is not None:
        query = query.limit(limit)
    rows = query.all()
    summary.scanned = len(rows)

    expired = [r for r in rows if _is_expired(r.expires_at, moment)]
    if dry_run:
        summary.deleted_rows = len(expired)
        logger.info(
            "maintenance.cleanup.revoked_tokens",
            extra={"event": "maintenance.cleanup.revoked_tokens"},
        )
        return summary

    for row in expired:
        session.delete(row)
        summary.deleted_rows += 1
    if summary.deleted_rows:
        session.commit()

    logger.info(
        "maintenance.cleanup.revoked_tokens",
        extra={"event": "maintenance.cleanup.revoked_tokens"},
    )
    return summary


def _safe_export_path(job_id: str, base: Path) -> Path | None:
    """Resolve the deletion target for ``job_id`` or ``None`` if unsafe.

    The target is *reconstructed* as ``base/<job_id>.jsonl`` — the stored
    ``ExportJob.file_path`` is never trusted for the unlink path. Rejects
    (returns ``None``) when the candidate, its parent, or any path it would
    resolve through is a symlink, or when the resolved path escapes
    ``base`` (path traversal via a crafted job id).
    """
    base_resolved = base.resolve()
    candidate = base / f"{job_id}.jsonl"

    # Refuse to follow a symlink anywhere on the candidate or its parents
    # up to base (checked pre-resolve so the target is never touched).
    probe = candidate
    while True:
        if probe.is_symlink():
            return None
        if probe == base_resolved or probe.parent == probe:
            break
        probe = probe.parent

    resolved = candidate.resolve()
    if not _is_within(base_resolved, resolved):
        return None
    if resolved == base_resolved or resolved.is_dir():
        return None
    return resolved


def cleanup_expired_export_jobs(
    session: Session,
    *,
    now: datetime | None = None,
    dry_run: bool = True,
    delete_files: bool = True,
    limit: int | None = None,
    exports_base: Path | None = None,
) -> CleanupSummary:
    """Hard-delete expired ``ExportJob`` rows after safe file unlink.

    Criteria: ``expires_at IS NOT NULL AND expires_at <= now``. Jobs with
    no expiry or a future expiry are preserved untouched.

    Real run, per expired job:

    * unsafe path (symlink / traversal / escapes ``exports_dir()``):
      file is **not** removed and the **row is preserved** and counted as
      ``skipped_unsafe`` — hiding the row would mask an operational problem.
    * file missing: counted ``missing_files``; row deleted (idempotent —
      already gone is success).
    * file present and safe: unlinked, counted ``deleted_files``; row
      deleted.

    ``dry_run=True`` (default) mutates no row and unlinks no file.
    ``delete_files=False`` keeps both the file and the row (report-only for
    the file branch) so a row is never orphaned from its file.
    ``audit_logs`` is never touched.
    """
    moment = _now(now)
    base = exports_base if exports_base is not None else exports_dir()
    summary = CleanupSummary(target="export_jobs", dry_run=dry_run)

    query = (
        session.query(ExportJob)
        .filter(ExportJob.expires_at.isnot(None))
        .order_by(ExportJob.expires_at.asc())
    )
    if limit is not None:
        query = query.limit(limit)
    rows = query.all()
    summary.scanned = len(rows)
    expired = [j for j in rows if _is_expired(j.expires_at, moment)]

    for job in expired:
        safe_path = _safe_export_path(job.id, base)
        if safe_path is None:
            summary.skipped_unsafe += 1
            summary.unsafe_ids.append(job.id)
            continue

        exists = safe_path.exists()
        if dry_run:
            if exists:
                summary.deleted_files += 1
            else:
                summary.missing_files += 1
            summary.deleted_rows += 1
            continue

        if not delete_files:
            # Operator opted out of file removal: leave file AND row so the
            # row never points at a now-orphaned file.
            summary.skipped_unsafe += 1
            continue

        if exists:
            try:
                safe_path.unlink()
                summary.deleted_files += 1
            except OSError:
                summary.errors += 1
                continue
        else:
            summary.missing_files += 1

        session.delete(job)
        summary.deleted_rows += 1

    if not dry_run and (summary.deleted_rows or summary.errors):
        session.commit()

    logger.info(
        "maintenance.cleanup.export_jobs",
        extra={"event": "maintenance.cleanup.export_jobs"},
    )
    return summary


def cleanup_expired_password_resets(session: Session, *, now: datetime | None = None,
                                   dry_run: bool = True, limit: int | None = None) -> CleanupSummary:
    moment = _now(now)
    summary = CleanupSummary(target="password_resets", dry_run=dry_run)
    query = session.query(PasswordReset).filter(PasswordReset.expires_at <= moment).order_by(PasswordReset.expires_at)
    if limit is not None:
        query = query.limit(limit)
    rows = query.all()
    summary.scanned = len(rows)
    if dry_run:
        summary.deleted_rows = len(rows)
    else:
        # Conditional delete cannot remove a replacement created after the SELECT.
        for row in rows:
            summary.deleted_rows += session.query(PasswordReset).filter(
                PasswordReset.user_id == row.user_id, PasswordReset.request_id == row.request_id,
                PasswordReset.expires_at <= moment).delete(synchronize_session=False)
        session.commit()
    return summary


def run_all(
    session: Session,
    *,
    now: datetime | None = None,
    dry_run: bool = True,
    limit: int | None = None,
) -> list[CleanupSummary]:
    moment = _now(now)
    return [
        cleanup_expired_password_resets(session, now=moment, dry_run=dry_run, limit=limit),
        cleanup_expired_revoked_tokens(
            session,
            now=moment,
            dry_run=dry_run,
            limit=limit,
        ),
        cleanup_expired_export_jobs(
            session,
            now=moment,
            dry_run=dry_run,
            limit=limit,
        ),
    ]


def run_target(
    session: Session,
    *,
    target: str = TARGET_ALL,
    now: datetime | None = None,
    dry_run: bool = True,
    limit: int | None = None,
) -> list[CleanupSummary]:
    moment = _now(now)
    if target == TARGET_ALL:
        return run_all(session, now=moment, dry_run=dry_run, limit=limit)
    if target == TARGET_PASSWORD_RESETS:
        return [cleanup_expired_password_resets(session, now=moment, dry_run=dry_run, limit=limit)]
    if target == TARGET_REVOKED_TOKENS:
        return [
            cleanup_expired_revoked_tokens(
                session,
                now=moment,
                dry_run=dry_run,
                limit=limit,
            )
        ]
    if target == TARGET_EXPORTS:
        return [
            cleanup_expired_export_jobs(
                session,
                now=moment,
                dry_run=dry_run,
                limit=limit,
            )
        ]
    raise ValueError(f"unknown cleanup target: {target}")


def _totals(summaries: list[CleanupSummary]) -> dict[str, int]:
    return {
        "scanned": sum(s.scanned for s in summaries),
        "deleted_rows": sum(s.deleted_rows for s in summaries),
        "deleted_files": sum(s.deleted_files for s in summaries),
        "missing_files": sum(s.missing_files for s in summaries),
        "skipped_unsafe": sum(s.skipped_unsafe for s in summaries),
        "errors": sum(s.errors for s in summaries),
    }


def _result_payload(
    *,
    target: str,
    dry_run: bool,
    limit: int | None,
    summaries: list[CleanupSummary],
    ok: bool = True,
    error: str | None = None,
) -> dict:
    payload = {
        "ok": ok,
        "target": target,
        "dry_run": dry_run,
        "limit": limit,
        "summaries": [s.as_dict() for s in summaries],
        "totals": _totals(summaries),
    }
    if error is not None:
        payload["error"] = error
    return payload


def _print_json(payload: dict, *, stream) -> None:
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")), file=stream)


def _print_summary(payload: dict, *, stream) -> None:
    mode = "dry-run" if payload["dry_run"] else "apply"
    limit = "none" if payload["limit"] is None else str(payload["limit"])
    print(
        f"status={'ok' if payload['ok'] else 'error'} "
        f"mode={mode} target={payload['target']} limit={limit}",
        file=stream,
    )
    for summary in payload["summaries"]:
        print(
            "target={target} scanned={scanned} deleted_rows={deleted_rows} "
            "deleted_files={deleted_files} missing_files={missing_files} "
            "skipped_unsafe={skipped_unsafe} errors={errors}".format(**summary),
            file=stream,
        )
    totals = payload["totals"]
    print(
        "total scanned={scanned} deleted_rows={deleted_rows} "
        "deleted_files={deleted_files} missing_files={missing_files} "
        "skipped_unsafe={skipped_unsafe} errors={errors}".format(**totals),
        file=stream,
    )
    if payload.get("error"):
        print("error=cleanup_failed", file=stream)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.maintenance.cleanup",
        description="Delete expired RevokedToken / ExportJob rows (7F-D ops).",
    )
    # Dry-run is the default; deletion requires an explicit --apply so an
    # accidental invocation can never destroy data.
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Actually delete (default: dry-run, mutate nothing).",
    )
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without mutating rows or files (default).",
    )
    parser.add_argument(
        "--target",
        choices=TARGET_CHOICES,
        default=TARGET_ALL,
        help="Cleanup target to run (default: all).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum rows to scan per selected target.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit one stable JSON object for scheduler/log parsing.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be a positive integer")
    dry_run = not args.apply

    # Local import: the CLI needs a real session, but importing the engine
    # at module load would couple `import app.maintenance.cleanup` (used by
    # tests with their own session) to DB configuration.
    from app.db import SessionLocal

    try:
        with SessionLocal() as session:
            summaries = run_target(
                session,
                target=args.target,
                dry_run=dry_run,
                limit=args.limit,
            )
    except Exception:
        logger.error(
            "maintenance.cleanup.failed",
            extra={"event": "maintenance.cleanup.failed", "target": args.target},
        )
        payload = _result_payload(
            target=args.target,
            dry_run=dry_run,
            limit=args.limit,
            summaries=[],
            ok=False,
            error="cleanup_failed",
        )
        if args.json:
            _print_json(payload, stream=sys.stderr)
        else:
            _print_summary(payload, stream=sys.stderr)
        return 1

    errors = _totals(summaries)["errors"]
    payload = _result_payload(
        target=args.target,
        dry_run=dry_run,
        limit=args.limit,
        summaries=summaries,
        ok=errors == 0,
    )
    if args.json:
        _print_json(payload, stream=sys.stdout)
    else:
        _print_summary(payload, stream=sys.stdout)
    return 1 if errors else 0


if __name__ == "__main__":  # pragma: no cover - thin shell
    raise SystemExit(main())
