import os
from uuid import UUID

from fastapi.testclient import TestClient

from services.api.main import app

client = TestClient(app)


def test_health_live_envelope():
    response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "outcome.v1"
    assert body["data"] == {"status": "alive", "service": "api", "contract_version": "outcome.v1"}
    assert response.headers["X-Correlation-ID"] == body["correlation_id"]
    UUID(body["correlation_id"])


def test_health_live_exposes_no_environment(monkeypatch):
    monkeypatch.setenv("CRUSTDATA_API_KEY", "sentinel-secret-value")

    text = client.get("/api/v1/health/live").text

    assert "sentinel-secret-value" not in text
    assert all(value not in text for key, value in os.environ.items() if key.endswith("_KEY") and len(value) > 8)


def test_unknown_route_uses_error_envelope():
    response = client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "NOT_FOUND"
    assert body["error"]["retryable"] is False
    assert response.headers["X-Correlation-ID"] == body["correlation_id"]
