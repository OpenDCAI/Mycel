import importlib

from fastapi.middleware.cors import CORSMiddleware

from backend.bootstrap import app_entrypoint


def test_chat_app_module_path_is_internalized():
    chat_app_main = importlib.import_module("backend.chat.app.main")
    assert chat_app_main.__name__ == "backend.chat.app.main"


def test_chat_app_mounts_chat_routes_only():
    chat_app_main = importlib.import_module("backend.chat.app.main")
    paths = {route.path for route in chat_app_main.app.routes}

    assert "/api/chats" in paths
    assert "/api/internal/messaging/display-users/{social_user_id}" in paths
    assert "/api/conversations" in paths
    assert "/api/relationships" in paths
    assert "/api/contacts" in paths
    assert "/api/users/chat-candidates" in paths


def test_chat_app_resolve_port_prefers_chat_backend_env(monkeypatch):
    chat_app_main = importlib.import_module("backend.chat.app.main")
    monkeypatch.setenv("LEON_CHAT_BACKEND_PORT", "55421")
    monkeypatch.setenv("PORT", "9000")

    assert chat_app_main._resolve_port() == 55421


def test_chat_app_resolve_port_uses_worktree_config_when_env_missing(monkeypatch):
    chat_app_main = importlib.import_module("backend.chat.app.main")
    monkeypatch.delenv("LEON_CHAT_BACKEND_PORT", raising=False)
    monkeypatch.delenv("PORT", raising=False)

    monkeypatch.setattr(
        app_entrypoint.subprocess,
        "run",
        lambda *_args, **_kwargs: __import__("subprocess").CompletedProcess(
            args=["git", "config"],
            returncode=0,
            stdout="55422\n",
            stderr="",
        ),
    )

    assert chat_app_main._resolve_port() == 55422


def test_chat_app_includes_permissive_cors_middleware():
    chat_app_main = importlib.import_module("backend.chat.app.main")
    assert any(middleware.cls is CORSMiddleware for middleware in chat_app_main.app.user_middleware)
