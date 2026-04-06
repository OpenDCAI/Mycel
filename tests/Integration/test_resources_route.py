from fastapi.testclient import TestClient

from backend.web.main import app
from backend.web.services import resource_service


def test_resources_overview_route_smoke():
    with TestClient(app) as client:
        response = client.get("/api/resources/overview")

    assert response.status_code == 200
    payload = response.json()
    assert "summary" in payload
    assert "providers" in payload
    assert "snapshot_at" in payload["summary"]
    assert "running_sessions" in payload["summary"]
    assert isinstance(payload["providers"], list)


def test_resources_overview_refresh_route_smoke():
    with TestClient(app) as client:
        response = client.post("/api/resources/overview/refresh")

    assert response.status_code == 200
    payload = response.json()
    assert "summary" in payload
    assert "providers" in payload
    assert "last_refreshed_at" in payload["summary"]
    assert "refresh_status" in payload["summary"]


def test_resources_sandbox_browse_route_uses_product_prefix(monkeypatch):
    monkeypatch.setattr(
        resource_service,
        "sandbox_browse",
        lambda lease_id, path: {"lease_id": lease_id, "current_path": path, "items": []},
    )

    with TestClient(app) as client:
        response = client.get("/api/resources/sandbox/lease-1/browse", params={"path": "/"})

    assert response.status_code == 200
    assert response.json() == {"lease_id": "lease-1", "current_path": "/", "items": []}


def test_resources_sandbox_read_route_uses_product_prefix(monkeypatch):
    monkeypatch.setattr(
        resource_service,
        "sandbox_read",
        lambda lease_id, path: {"lease_id": lease_id, "path": path, "content": "hello", "truncated": False},
    )

    with TestClient(app) as client:
        response = client.get("/api/resources/sandbox/lease-1/read", params={"path": "/README.md"})

    assert response.status_code == 200
    assert response.json() == {
        "lease_id": "lease-1",
        "path": "/README.md",
        "content": "hello",
        "truncated": False,
    }
