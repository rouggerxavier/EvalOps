from fastapi.testclient import TestClient

from app.main import app


def test_liveness() -> None:
    client = TestClient(app)
    response = client.get("/health/liveness")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness() -> None:
    client = TestClient(app)
    response = client.get("/health/readiness")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

