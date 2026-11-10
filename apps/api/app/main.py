import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import inspect, text

from app.api.routes import router as v1_router
from app.api.routes_auth import router as auth_router
from app.api.routes_rubrics import router as rubrics_router
from app.api.routes_evaluations import router as evaluations_router
from app.api.routes_phase5 import router as phase5_router
from app.api.routes_phase6 import router as phase6_router
from app.api.routes_trace_actions import router as trace_actions_router
from app.api.routes_quality_gate import router as quality_gate_router
from app.api.routes_sampling import router as sampling_router
from app.api.routes_tasks import router as tasks_router
from app.api.routes_investigations import router as investigations_router
from app.config import max_body_bytes
from app.db import Base, SessionLocal, engine, ensure_schema_compatibility
from app.logging_config import access_logger, configure_logging
from app.request_id import reset_request_context, sanitize_request_id, set_request_context, set_request_org, set_request_user


def _use_alembic() -> bool:
    """Pick schema-management strategy at startup.

    ``EVALOPS_USE_ALEMBIC=1`` runs ``alembic upgrade head`` instead of
    ``Base.metadata.create_all``. Production should opt in; tests and
    local SQLite dev keep ``create_all`` (the suite recreates the DB by
    deleting ``evalops.db*`` between runs, which is incompatible with
    Alembic's ``alembic_version`` row).

    See ``docs/ops/database-migrations.md``.
    """
    return os.getenv("EVALOPS_USE_ALEMBIC", "").lower() in {"1", "true", "yes"}


def _run_alembic_upgrade() -> None:
    from alembic import command
    from alembic.config import Config

    api_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = Config(os.path.join(api_root, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(api_root, "alembic"))
    command.upgrade(cfg, "head")


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    if _use_alembic():
        _run_alembic_upgrade()
    else:
        existing = inspect(engine)
        if existing.has_table("datasets") and "task_type" not in {column["name"] for column in existing.get_columns("datasets")}:
            raise RuntimeError("task_schema_migration_required: back up and apply Alembic 0014 before starting this version; see docs/ops/database-migrations.md")
        Base.metadata.create_all(bind=engine)
        ensure_schema_compatibility()
    from app.workers.queue import create_arq_pool, close_arq_pool

    app.state.arq_pool = await create_arq_pool()
    try:
        yield
    finally:
        await close_arq_pool(app.state.arq_pool)
        app.state.arq_pool = None


app = FastAPI(title="EvalOps API", version="0.1.0", lifespan=lifespan)


@app.exception_handler(RequestValidationError)
async def _validation_error(request: Request, exc: RequestValidationError):
    if request.method == "POST" and _route_template(request) == "/v1/auth/change-password":
        # FastAPI's default validation body includes input, which can contain passwords.
        return JSONResponse(status_code=422, content={"detail": "invalid_password"})
    if request.url.path.endswith(("/datasets", "/experiments")):
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        if isinstance(payload, dict) and (payload.get("task_type") == "regression" or payload.get("kind") == "task_comparison"):
            return JSONResponse(status_code=422, content={"detail": "invalid_task_payload"})
    if request.url.path.startswith("/v1/") and any(part in request.url.path for part in ("task-", "prediction-sets", "model-versions", "snapshots", "service-principals", "/cases", "investigations", "/classify")):
        return JSONResponse(status_code=422, content={"detail": "invalid_task_payload"})
    return await request_validation_exception_handler(request, exc)


def _route_template(request: Request) -> str | None:
    route = request.scope.get("route")
    if route is None:
        return None
    return getattr(route, "path", None) or getattr(route, "path_format", None)


@app.middleware("http")
async def body_size_limit(request: Request, call_next):
    """Reject payloads larger than ``EVALOPS_MAX_BODY_BYTES`` with HTTP 413.

    Honours ``Content-Length`` when present (cheap path). For requests
    without a declared length (e.g., chunked transfer) the body is buffered
    and measured. Buffering is acceptable for the API surface but production
    deployments behind nginx/cloudflare should also enforce a reverse-proxy
    cap to avoid memory pressure on legitimately large chunked streams.
    """
    limit = max_body_bytes()
    if request.method == "POST" and request.url.path.endswith(("/prediction-sets", "/datasets")):
        limit = 10 * 1024 * 1024
    declared = request.headers.get("content-length")
    if declared is not None:
        try:
            if int(declared) > limit:
                return JSONResponse(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    content={"detail": "payload_too_large", "limit_bytes": limit},
                )
        except ValueError:
            pass

    body = await request.body()
    if len(body) > limit:
        return JSONResponse(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            content={"detail": "payload_too_large", "limit_bytes": limit},
        )

    return await call_next(request)


@app.middleware("http")
async def _request_context_middleware(request: Request, call_next):
    """Attach request context and log JSON request lifecycle events."""
    t0 = time.monotonic()
    rid = sanitize_request_id(request.headers.get("x-request-id"))
    request.state.request_id = rid
    context_tokens = set_request_context(request_id=rid)
    status_code = 500
    exc_summary: str | None = None
    try:
        access_logger.info(
            "request.start",
            extra={
                "request_id": rid,
                "method": request.method,
                "path": request.url.path,
                "route": _route_template(request),
            },
        )
        response = await call_next(request)
        status_code = response.status_code
        response.headers["X-Request-ID"] = rid
        return response
    except Exception as exc:
        exc_summary = type(exc).__name__
        raise
    finally:
        latency_ms = round((time.monotonic() - t0) * 1000, 1)
        user_id = getattr(request.state, "user_id", None)
        org_id = getattr(request.state, "org_id", None)
        if user_id:
            set_request_user(user_id)
        if org_id:
            set_request_org(org_id)
        extra: dict = {
            "request_id": rid,
            "method": request.method,
            "path": request.url.path,
            "route": _route_template(request),
            "status_code": status_code,
            "latency_ms": latency_ms,
        }
        if user_id:
            extra["user_id"] = user_id
        if org_id:
            extra["org_id"] = org_id
        if exc_summary:
            extra["error"] = exc_summary
        access_logger.info("request.end", extra=extra)
        reset_request_context(context_tokens)


app.include_router(auth_router)
app.include_router(v1_router)
app.include_router(rubrics_router)
app.include_router(evaluations_router)
app.include_router(tasks_router)
app.include_router(investigations_router)
app.include_router(phase5_router)
app.include_router(phase6_router)
app.include_router(trace_actions_router)
app.include_router(quality_gate_router)
app.include_router(sampling_router)


@app.get("/health/liveness")
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/readiness")
async def readiness() -> dict[str, str]:
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content={"status": "not_ready"})
    return {"status": "ok"}
