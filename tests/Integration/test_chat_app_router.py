from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.chat.api.http import app_router as owner_chat_app_router


def test_chat_app_router_owner_module_lives_under_backend_chat() -> None:
    assert owner_chat_app_router.__name__ == "backend.chat.api.http.app_router"


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
    assert "/api/contacts" in paths
    assert "/api/users/chat-candidates" in paths
