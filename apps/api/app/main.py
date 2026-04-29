from fastapi import FastAPI

from app.api.routes import router as v1_router
from app.db import Base, engine

app = FastAPI(title="EvalOps API", version="0.1.0")
app.include_router(v1_router)


@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(bind=engine)


@app.get("/health/liveness")
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/readiness")
async def readiness() -> dict[str, str]:
    return {"status": "ok"}
