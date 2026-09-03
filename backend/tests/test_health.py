from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_process_status() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "credible-backend",
    }


def test_ready_returns_current_dependency_checks() -> None:
    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": [
            {
                "name": "application",
                "status": "ok",
            }
        ],
    }


def test_openapi_exposes_health_routes() -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/health" in paths
    assert "/ready" in paths
