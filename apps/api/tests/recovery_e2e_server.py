"""Opt-in local fake mailbox for Playwright. Never imports/sends via SMTP."""
import os
import uuid

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


def main():
    assert os.environ.get("E2E_RECOVERY") == "1", "local recovery E2E opt-in required"
    target = os.environ["ACCOUNT_TEST_DATABASE_URL"]
    url = make_url(target)
    assert (url.get_backend_name(), url.host, url.port, url.database, url.username) == (
        "postgresql", "127.0.0.1", 15633, "evalops_account_test", "evalops")
    assert os.environ.get("REDIS_URL") == "redis://127.0.0.1:18683/15"
    schema = "recovery_e2e_" + uuid.uuid4().hex
    admin = create_engine(target)
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    os.environ.update(DATABASE_URL=target, PGOPTIONS="-csearch_path=" + schema, APP_ENV="test",
                      EVALOPS_SMTP_HOST="smtp.example.invalid", EVALOPS_SMTP_FROM="test@example.invalid",
                      EVALOPS_PUBLIC_ORIGIN="http://127.0.0.1:3134")
    from app.db import SessionLocal, engine
    from app.main import app
    from app.workers import queue
    from app.workers.password_recovery_worker import send_password_reset_job
    import uvicorn
    inbox = {}
    def fake_mailer(config, recipient, token):
        inbox[recipient] = {"link": config.public_origin + "/reset-password#" + token}
    class FakePool:
        async def ping(self):
            return True
        async def enqueue_job(self, name, *args, **kwargs):
            assert name == "send_password_reset_job"
            await send_password_reset_job({"db_session_factory": SessionLocal, "recovery_mailer": fake_mailer}, *args)
            return object()
        async def aclose(self):
            pass
    async def create_fake_pool():
        return FakePool()
    queue.create_arq_pool = create_fake_pool
    @app.get("/_test/inbox", include_in_schema=False)
    def fake_inbox(email: str):
        return inbox.get(email, {})
    try:
        uvicorn.run(app, host="127.0.0.1", port=18143, access_log=False, proxy_headers=False)
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


if __name__ == "__main__":
    main()
