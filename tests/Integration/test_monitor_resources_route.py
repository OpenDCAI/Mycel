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


def test_monitor_and_product_resource_routes_coexist_intentionally():
    with TestClient(app) as client:
        monitor_response = client.get("/api/monitor/resources")
        product_response = client.get("/api/resources/overview")

    assert monitor_response.status_code == 200
    assert product_response.status_code == 200


def test_monitor_health_route_smoke():
    with TestClient(app) as client:
        response = client.get("/api/monitor/health")

    assert response.status_code == 200
    payload = response.json()
    assert "snapshot_at" in payload
    assert "db" in payload
    assert "sessions" in payload


def test_monitor_dashboard_route_smoke():
    with TestClient(app) as client:
        response = client.get("/api/monitor/dashboard")

    assert response.status_code == 200
    payload = response.json()
    assert "snapshot_at" in payload
    assert "resources_summary" in payload
    assert "infra" in payload
    assert "workload" in payload
    assert "latest_evaluation" in payload


def test_monitor_leases_route_exposes_summary_and_groups():
    with TestClient(app) as client:
        response = client.get("/api/monitor/leases")

    assert response.status_code == 200
    payload = response.json()
    assert "summary" in payload
    assert "groups" in payload
    assert "triage" in payload
    assert set(payload["summary"]).issuperset({"total", "healthy", "diverged", "orphan", "orphan_diverged"})
    assert isinstance(payload["groups"], list)
    assert set(payload["triage"]["summary"]).issuperset(
        {"total", "active_drift", "detached_residue", "orphan_cleanup", "healthy_capacity"}
    )
    assert isinstance(payload["triage"]["groups"], list)
