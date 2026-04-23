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


def test_chat_openapi_keeps_public_and_internal_send_message_schemas_distinct() -> None:
    app = FastAPI()
    app.include_router(owner_chat_app_router.router)

    with TestClient(app) as client:
        response = client.get("/openapi.json")

    assert response.status_code == 200
    schemas = response.json()["components"]["schemas"]

    assert schemas["SendMessageBody"]["title"] == "SendMessageBody"
    assert schemas["InternalSendMessageBody"]["title"] == "InternalSendMessageBody"
