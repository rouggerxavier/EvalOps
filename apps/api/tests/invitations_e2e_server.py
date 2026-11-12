"""Opt-in R2 integration API: real PG/Redis/auth/worker, in-memory SMTP only.

Start with E2E_INVITATIONS_REAL=1, MEMBERSHIP_TEST_DATABASE_URL targeting
127.0.0.1:15634/evalops_membership_test, REDIS_URL=redis://127.0.0.1:18684/14.
Run Next dev on 3136 with EVALOPS_API_BASE_URL=http://127.0.0.1:18146/v1.
Test controls are loopback-only and exist solely in this opt-in process.
"""
import os
import signal
import sys
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


def main():
    assert os.environ.get("E2E_INVITATIONS_REAL") == "1"
    target = os.environ["MEMBERSHIP_TEST_DATABASE_URL"]
    url = make_url(target)
    assert (url.get_backend_name(), url.host, url.port, url.database, url.username) == (
        "postgresql", "127.0.0.1", 15634, "evalops_membership_test", "evalops")
    assert os.environ.get("REDIS_URL") == "redis://127.0.0.1:18684/14"
    schema = "invitations_e2e_" + uuid.uuid4().hex
    admin = create_engine(target)
    with admin.begin() as conn:
        assert conn.execute(text("SHOW server_version_num")).scalar().startswith("16")
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    os.environ.update(DATABASE_URL=target, PGOPTIONS="-csearch_path=" + schema, APP_ENV="test",
                      EVALOPS_INVITATIONS_ENABLED="true", EVALOPS_USE_ALEMBIC="0",
                      EVALOPS_SMTP_HOST="smtp.example.invalid", EVALOPS_SMTP_FROM="test@example.invalid",
                      EVALOPS_PUBLIC_ORIGIN="http://127.0.0.1:3136")
    from app.db import Base, SessionLocal, engine
    from app.main import app
    from app.models import Membership, Organization, OrganizationInvitation, Project, Trace, User
    from app.security import create_session_token, decode_access_token
    from app.workers import invitation_worker, queue
    import uvicorn

    inbox, calls, jobs = {}, [], []
    # Random org ID scopes real Redis quota keys to this process; no FLUSHDB.
    org_id = "e2e_" + uuid.uuid4().hex
    roles = {"owner": "owner", "member": "member", "viewer": "viewer", "unknown": "legacy"}

    def fake_smtp(config, message, recipient):
        assert config.host == "smtp.example.invalid"
        inbox[recipient] = {"body": message.get_content(), "to": str(message["To"]),
                            "subject": str(message["Subject"])}
    invitation_worker.send_message = fake_smtp

    class FakePool:
        async def ping(self):
            return True
        async def enqueue_job(self, name, *args, **kwargs):
            assert name == "send_invitation_job" and len(args) == 1 and kwargs["_job_id"] == args[0]
            jobs.append({"name": name, "args": args})
            await invitation_worker.send_invitation_job({"db_session_factory": SessionLocal}, *args)
            return object()
        async def aclose(self):
            pass
    async def create_fake_pool():
        return FakePool()
    queue.create_arq_pool = create_fake_pool

    @app.middleware("http")
    async def observe(request, call_next):
        if request.url.path.startswith("/v1/"):
            try:
                user = decode_access_token(request.headers.get("authorization", "").removeprefix("Bearer ")).get("sub")
            except Exception:
                user = None
            calls.append({"method": request.method, "path": request.url.path.removeprefix("/v1"), "user": user})
        return await call_next(request)

    @app.post("/_test/reset", include_in_schema=False)
    def reset():
        nonlocal org_id
        org_id = "e2e_" + uuid.uuid4().hex
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
        inbox.clear(); calls.clear(); jobs.clear()
        with SessionLocal() as db:
            db.add(Organization(id=org_id, name="R2 QA", slug="org"))
            for user in [*roles, "recipient", "recipient2"]:
                db.add(User(id=user, email=user + "@example.invalid", name=user.title() + " QA"))
            db.flush()
            for user, role in roles.items():
                db.add(Membership(user_id=user, organization_id=org_id, role=role))
            db.add(Project(id="project", organization_id=org_id, slug="project", name="QA Project"))
            db.flush()
            now = datetime.now(timezone.utc)
            db.add(Trace(id="trace", project_id="project", organization_id=org_id, name="QA Trace",
                         environment="development", status="success", started_at=now, ended_at=now, duration_ms=1))
            db.commit()
        return {"organization_id": org_id}

    @app.get("/_test/session/{user}", include_in_schema=False)
    def session(user: str):
        assert user in [*roles, "recipient", "recipient2"]
        return {"token": create_session_token(sub=user, email=user + "@example.invalid", name=user.title() + " QA")}

    @app.get("/_test/inbox", include_in_schema=False)
    def mailbox(email: str):
        return inbox.get(email, {})

    @app.post("/_test/membership/{user}/{role}", include_in_schema=False)
    def membership(user: str, role: str):
        assert user in [*roles, "recipient", "recipient2"] and role in {"owner", "member", "viewer", "legacy"}
        with SessionLocal() as db:
            row = db.get(Membership, (user, org_id))
            if row:
                row.role = role
            else:
                db.add(Membership(user_id=user, organization_id=org_id, role=role))
            db.commit()
        return {"ok": True}

    @app.post("/_test/expire", include_in_schema=False)
    def expire(email: str):
        # Moves the fixed 24h deadline into the past; no other state changes.
        with SessionLocal() as db:
            rows = db.query(OrganizationInvitation).filter_by(organization_id=org_id, email=email).all()
            for row in rows:
                row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            db.commit()
        return {"expired": len(rows)}

    @app.get("/_test/state", include_in_schema=False)
    def state():
        with SessionLocal() as db:
            memberships = {m.user_id: m.role for m in db.query(Membership).all()}
        return {"calls": calls, "jobs": jobs, "memberships": memberships}

    # uvicorn re-raises SIGTERM after shutdown; turn it into SystemExit so the schema drop runs.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    try:
        uvicorn.run(app, host="127.0.0.1", port=18146, access_log=False, proxy_headers=False)
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


if __name__ == "__main__":
    main()
