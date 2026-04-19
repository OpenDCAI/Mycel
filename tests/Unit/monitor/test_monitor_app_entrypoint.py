from fastapi.testclient import TestClient

from backend.monitor_app.main import app


def test_monitor_app_mounts_only_global_monitor_routes():
    with TestClient(app) as client:
        response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]

    assert "/api/monitor/resources" in paths
    assert "/api/monitor/sandboxes" in paths
    assert "/api/monitor/threads" not in paths
    assert "/api/monitor/threads/{thread_id}" not in paths
    assert "/api/monitor/evaluation/batches/{batch_id}/start" not in paths
