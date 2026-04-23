from __future__ import annotations

from backend.chat import messaging_client


def test_http_messaging_service_client_resolves_display_user(monkeypatch):
    captured: dict[str, object] = {}

    class _Response:
        def raise_for_status(self) -> None:
            captured["raised"] = True

        def json(self) -> dict[str, object]:
            return {
                "id": "user-1",
                "type": "human",
                "display_name": "Human",
                "owner_user_id": None,
                "avatar_url": "https://example/avatar.png",
            }

    class _Client:
        def __init__(self, *, base_url: str, timeout: float, trust_env: bool) -> None:
            captured["base_url"] = base_url
            captured["timeout"] = timeout
            captured["trust_env"] = trust_env

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def get(self, path: str, *, params: dict | None = None) -> _Response:
            captured["path"] = path
            captured["params"] = params
            return _Response()

    monkeypatch.setattr(messaging_client.httpx, "Client", _Client)

    client = messaging_client.HttpMessagingServiceClient(base_url="http://chat-backend")
    user = client.resolve_display_user("user-1")

    assert captured == {
        "base_url": "http://chat-backend",
        "timeout": 10.0,
        "trust_env": False,
        "path": "/api/internal/messaging/display-users/user-1",
        "params": None,
        "raised": True,
    }
    assert user.id == "user-1"
    assert user.type == "human"
    assert user.display_name == "Human"
    assert user.owner_user_id is None
    assert user.avatar_url == "https://example/avatar.png"


def test_http_messaging_service_client_posts_send_message(monkeypatch):
    captured: dict[str, object] = {}

    class _Response:
        def raise_for_status(self) -> None:
            captured["raised"] = True

        def json(self) -> dict[str, object]:
            return {"id": "msg-1", "chat_id": "chat-1", "sender_id": "agent-1", "content": "hello"}

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

    monkeypatch.setattr(messaging_client.httpx, "Client", _Client)

    client = messaging_client.HttpMessagingServiceClient(base_url="http://chat-backend")
    message = client.send(
        "chat-1",
        "agent-1",
        "hello",
        mentions=["user-1"],
        signal="yield",
        enforce_caught_up=True,
    )

    assert captured == {
        "base_url": "http://chat-backend",
        "timeout": 10.0,
        "trust_env": False,
        "path": "/api/internal/messaging/chats/chat-1/messages/send",
        "json": {
            "sender_id": "agent-1",
            "content": "hello",
            "message_type": "human",
            "content_type": "text",
            "mentions": ["user-1"],
            "signal": "yield",
            "reply_to": None,
            "ai_metadata": None,
            "enforce_caught_up": True,
        },
        "raised": True,
    }
    assert message["id"] == "msg-1"


def test_http_messaging_service_client_returns_none_for_missing_display_user(monkeypatch):
    class _Response:
        status_code = 404

        def raise_for_status(self) -> None:
            raise messaging_client.httpx.HTTPStatusError(
                "not found",
                request=messaging_client.httpx.Request("GET", "http://chat-backend"),
                response=messaging_client.httpx.Response(404),
            )

    class _Client:
        def __init__(self, *, base_url: str, timeout: float, trust_env: bool) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def get(self, path: str, *, params: dict | None = None) -> _Response:
            return _Response()

    monkeypatch.setattr(messaging_client.httpx, "Client", _Client)

    client = messaging_client.HttpMessagingServiceClient(base_url="http://chat-backend")

    assert client.resolve_display_user("missing-user") is None
