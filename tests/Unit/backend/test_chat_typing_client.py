from __future__ import annotations

from backend.chat import typing_client


def test_http_typing_tracker_posts_start_chat_without_proxy_env(monkeypatch):
    captured: dict[str, object] = {}

    class _Response:
        def raise_for_status(self) -> None:
            captured["raised"] = True

    class _Client:
        def __init__(self, *, base_url: str, timeout: float, trust_env: bool) -> None:
            captured["base_url"] = base_url
            captured["timeout"] = timeout
            captured["trust_env"] = trust_env

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def post(self, path: str, *, json: dict) -> _Response:
            captured["path"] = path
            captured["json"] = json
            return _Response()

    monkeypatch.setattr(typing_client.httpx, "Client", _Client)

    tracker = typing_client.HttpTypingTracker(base_url="http://chat-backend")
    tracker.start_chat("thread-1", "chat-1", "agent-1")

    assert captured == {
        "base_url": "http://chat-backend",
        "timeout": 10.0,
        "trust_env": False,
        "path": "/api/internal/realtime/typing/start",
        "json": {"thread_id": "thread-1", "chat_id": "chat-1", "user_id": "agent-1"},
        "raised": True,
    }


def test_http_typing_tracker_posts_stop_without_proxy_env(monkeypatch):
    captured: dict[str, object] = {}

    class _Response:
        def raise_for_status(self) -> None:
            captured["raised"] = True

    class _Client:
        def __init__(self, *, base_url: str, timeout: float, trust_env: bool) -> None:
            captured["base_url"] = base_url
            captured["timeout"] = timeout
            captured["trust_env"] = trust_env

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def post(self, path: str, *, json: dict) -> _Response:
            captured["path"] = path
            captured["json"] = json
            return _Response()

    monkeypatch.setattr(typing_client.httpx, "Client", _Client)

    tracker = typing_client.HttpTypingTracker(base_url="http://chat-backend")
    tracker.stop("thread-1")

    assert captured == {
        "base_url": "http://chat-backend",
        "timeout": 10.0,
        "trust_env": False,
        "path": "/api/internal/realtime/typing/stop",
        "json": {"thread_id": "thread-1"},
        "raised": True,
    }
