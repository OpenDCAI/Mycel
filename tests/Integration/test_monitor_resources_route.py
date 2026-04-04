from fastapi.testclient import TestClient

from backend.web.main import app


def test_monitor_resources_route_smoke():
    with TestClient(app) as client:
        response = client.get("/api/monitor/resources")

    assert response.status_code == 200
    payload = response.json()
    assert "summary" in payload
    assert "providers" in payload
    assert "snapshot_at" in payload["summary"]
    assert "running_sessions" in payload["summary"]
    assert isinstance(payload["providers"], list)


def test_monitor_resources_refresh_route_smoke():
    with TestClient(app) as client:
        response = client.post("/api/monitor/resources/refresh")

    assert response.status_code == 200
    payload = response.json()
    assert "summary" in payload
    assert "providers" in payload
    assert "last_refreshed_at" in payload["summary"]
    assert "refresh_status" in payload["summary"]


def test_monitor_health_route_smoke():
    with TestClient(app) as client:
        response = client.get("/api/monitor/health")

    assert response.status_code == 200
    payload = response.json()
    assert "snapshot_at" in payload
    assert "db" in payload
    assert "sessions" in payload
