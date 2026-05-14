from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.routes import router as v1_router
from app.api.routes_auth import router as auth_router
from app.api.routes_rubrics import router as rubrics_router
from app.api.routes_evaluations import router as evaluations_router
from app.api.routes_phase5 import router as phase5_router
from app.api.routes_phase6 import router as phase6_router
from app.config import max_body_bytes
from app.db import Base, SessionLocal, engine, ensure_schema_compatibility

@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    ensure_schema_compatibility()
    yield


app = FastAPI(title="EvalOps API", version="0.1.0", lifespan=lifespan)


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

    async def _receive():
        return {"type": "http.request", "body": body, "more_body": False}

    request._receive = _receive  # type: ignore[attr-defined]
    return await call_next(request)


app.include_router(auth_router)
app.include_router(v1_router)
app.include_router(rubrics_router)
app.include_router(evaluations_router)
app.include_router(phase5_router)
app.include_router(phase6_router)


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
