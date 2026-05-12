from contextlib import asynccontextmanager

from fastapi import FastAPI, status
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.routes import router as v1_router
from app.api.routes_auth import router as auth_router
from app.api.routes_rubrics import router as rubrics_router
from app.api.routes_evaluations import router as evaluations_router
from app.api.routes_phase5 import router as phase5_router
from app.api.routes_phase6 import router as phase6_router
from app.db import Base, SessionLocal, engine, ensure_schema_compatibility

@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    ensure_schema_compatibility()
    yield


app = FastAPI(title="EvalOps API", version="0.1.0", lifespan=lifespan)
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
