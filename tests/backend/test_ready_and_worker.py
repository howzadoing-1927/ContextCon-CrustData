from fastapi.testclient import TestClient

import pytest

from services.api.main import create_app
from services.core import db
from services.core.config import get_settings
from services.worker.main import AnotherWorkerActive, write_heartbeat


@pytest.fixture
def runtime_tenant(make_tenant, monkeypatch):
    tenant = make_tenant()
    monkeypatch.setenv("RUNTIME_ORGANIZATION_ID", str(tenant.organization_id))
    monkeypatch.setenv("WORKER_STALE_SECONDS", "60")
    get_settings.cache_clear()
    db.reset_pool()
    yield tenant
    db.reset_pool()
    get_settings.cache_clear()


def test_ready_with_fresh_worker_heartbeat(runtime_tenant, conn):
    write_heartbeat(conn, get_settings(), "pytest-worker")

    response = TestClient(create_app()).get("/api/v1/health/ready")

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["status"] == "ready" and data["database"] == "ok" and data["worker"] == "fresh"
    assert 0 <= data["last_seen_age_seconds"] <= 5


def test_ready_is_503_without_or_with_stale_heartbeat(runtime_tenant, conn):
    missing = TestClient(create_app()).get("/api/v1/health/ready")
    write_heartbeat(conn, get_settings(), "pytest-worker")
    conn.execute(
        "update public.organizations set runtime_json = jsonb_set(runtime_json, '{worker,last_seen_at}', "
        "to_jsonb(now() - interval '10 minutes')) where id = %s",
        (runtime_tenant.organization_id,),
    )
    stale = TestClient(create_app()).get("/api/v1/health/ready")

    assert missing.status_code == 503 and missing.json()["error"]["details"]["worker"] == "missing"
    assert stale.status_code == 503 and stale.json()["error"]["details"]["worker"] == "stale"


def test_ready_is_503_when_database_unreachable(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://outcome:x@127.0.0.1:1/unreachable")
    get_settings.cache_clear()
    db.reset_pool()
    try:
        response = TestClient(create_app()).get("/api/v1/health/ready")
    finally:
        db.reset_pool()
        get_settings.cache_clear()

    assert response.status_code == 503
    assert response.json()["error"]["details"] == {
        "status": "not_ready", "database": "error", "worker": "unknown", "last_seen_age_seconds": None,
    }
    assert "127.0.0.1" not in response.text


def test_second_worker_refused_while_first_is_fresh(runtime_tenant, conn):
    settings = get_settings()
    write_heartbeat(conn, settings, "worker-1")

    with pytest.raises(AnotherWorkerActive):
        write_heartbeat(conn, settings, "worker-2")

    conn.execute(
        "update public.organizations set runtime_json = jsonb_set(runtime_json, '{worker,last_seen_at}', "
        "to_jsonb(now() - interval '10 minutes')) where id = %s",
        (runtime_tenant.organization_id,),
    )
    write_heartbeat(conn, settings, "worker-2")
    worker = conn.execute(
        "select runtime_json -> 'worker' ->> 'worker_id' as id from public.organizations where id = %s",
        (runtime_tenant.organization_id,),
    ).fetchone()
    assert worker["id"] == "worker-2"
