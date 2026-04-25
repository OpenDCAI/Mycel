from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.chat.api.http import app_router as owner_chat_app_router


def test_chat_app_router_mounts_chat_relationship_and_conversation_routes() -> None:
    app = FastAPI()
    app.include_router(owner_chat_app_router.router)

    with TestClient(app) as client:
        response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]

    assert "/api/chats" in paths
    assert "/api/relationships" in paths
    assert "/api/conversations" in paths


def test_chat_app_router_does_not_mount_internal_http_surface() -> None:
    app = FastAPI()
    app.include_router(owner_chat_app_router.router)

    with TestClient(app) as client:
        response = client.get("/openapi.json")

    assert response.status_code == 200
    spec = response.json()

    forbidden_prefix = "/api/" + "internal"
    forbidden_schema = "Internal" + "SendMessageBody"

    assert not [path for path in spec["paths"] if path.startswith(forbidden_prefix)]
    assert forbidden_schema not in spec.get("components", {}).get("schemas", {})
