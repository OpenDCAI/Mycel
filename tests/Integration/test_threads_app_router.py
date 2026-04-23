import importlib
import inspect

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.threads.api.http import app_router as owner_threads_app_router
from backend.threads.api.http import runtime_router as owner_threads_runtime_router


def test_threads_app_router_owner_module_lives_under_backend_threads() -> None:
    assert owner_threads_app_router.__name__ == "backend.threads.api.http.app_router"


def test_threads_runtime_router_owner_module_lives_under_backend_threads() -> None:
    assert owner_threads_runtime_router.__name__ == "backend.threads.api.http.runtime_router"


def test_threads_runtime_router_does_not_import_web_threads_router() -> None:
    runtime_router_source = inspect.getsource(importlib.import_module("backend.threads.api.http.runtime_router"))

    assert "backend.web.routers" not in runtime_router_source


def test_threads_app_router_mounts_primary_thread_routes() -> None:
    app = FastAPI()
    app.include_router(owner_threads_app_router.router)

    with TestClient(app) as client:
        response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]

    assert "/api/threads" in paths
    assert "/api/threads/main" in paths
    assert "/api/threads/default-config" in paths
    assert "/api/threads/{thread_id}" in paths
    assert "/api/threads/{thread_id}/messages" in paths
    assert "/api/threads/{thread_id}/queue" in paths
    assert "/api/threads/{thread_id}/history" in paths
    assert "/api/threads/{thread_id}/permissions" in paths
    assert "/api/threads/{thread_id}/permissions/{request_id}/resolve" in paths
    assert "/api/threads/{thread_id}/permissions/rules" in paths
    assert "/api/threads/{thread_id}/permissions/rules/{behavior}/{tool_name}" in paths
    assert "/api/threads/{thread_id}/runtime" in paths
    assert "/api/threads/{thread_id}/sandbox" in paths
    assert "/api/threads/{thread_id}/events" in paths
    assert "/api/threads/{thread_id}/runs/cancel" in paths
    assert "/api/threads/{thread_id}/tasks" in paths
    assert "/api/threads/{thread_id}/tasks/{task_id}" in paths
    assert "/api/threads/{thread_id}/tasks/{task_id}/cancel" in paths
    assert "/api/threads/{thread_id}/files/list" in paths
    assert "/api/internal/agent-runtime/chat-deliveries" in paths
    assert "/api/internal/agent-runtime/thread-input" in paths
    assert "/api/internal/thread-runtime/activities" in paths
    assert "/api/internal/thread-runtime/conversations/hire" in paths
    assert "/api/internal/identity/agent-actors/{social_user_id}/exists" in paths
