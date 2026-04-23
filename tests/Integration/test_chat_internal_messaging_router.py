from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.chat.api.http import internal_messaging_router


def test_internal_messaging_router_dispatches_display_user_and_send_message() -> None:
    seen: list[tuple[str, object]] = []

    class _MessagingService:
        def resolve_display_user(self, social_user_id: str):
            seen.append(("resolve_display_user", social_user_id))
            return SimpleNamespace(
                id=social_user_id,
                type="human",
                display_name="Human",
                owner_user_id=None,
                avatar_url="https://example/avatar.png",
            )

        def send(
            self,
            chat_id: str,
            sender_id: str,
            content: str,
            *,
            message_type: str = "human",
            content_type: str = "text",
            mentions: list[str] | None = None,
            signal: str | None = None,
            reply_to: str | None = None,
            ai_metadata: dict | None = None,
            enforce_caught_up: bool = False,
        ):
            seen.append(
                (
                    "send",
                    {
                        "chat_id": chat_id,
                        "sender_id": sender_id,
                        "content": content,
                        "message_type": message_type,
                        "content_type": content_type,
                        "mentions": mentions,
                        "signal": signal,
                        "reply_to": reply_to,
                        "ai_metadata": ai_metadata,
                        "enforce_caught_up": enforce_caught_up,
                    },
                )
            )
            return {
                "id": "msg-1",
                "chat_id": chat_id,
                "sender_id": sender_id,
                "content": content,
            }

        def mark_read(self, chat_id: str, user_id: str) -> None:
            seen.append(("mark_read", {"chat_id": chat_id, "user_id": user_id}))

    app = FastAPI()
    app.state.chat_runtime_state = SimpleNamespace(messaging_service=_MessagingService())
    app.include_router(internal_messaging_router.router)

    with TestClient(app) as client:
        user_response = client.get("/api/internal/messaging/display-users/user-1")
        send_response = client.post(
            "/api/internal/messaging/chats/chat-1/messages/send",
            json={
                "sender_id": "agent-1",
                "content": "hello",
                "mentions": ["user-1"],
                "signal": "yield",
                "enforce_caught_up": True,
            },
        )
        read_response = client.post(
            "/api/internal/messaging/chats/chat-1/read",
            json={"user_id": "agent-1"},
        )

    assert user_response.status_code == 200
    assert user_response.json() == {
        "id": "user-1",
        "type": "human",
        "display_name": "Human",
        "owner_user_id": None,
        "avatar_url": "https://example/avatar.png",
    }
    assert send_response.status_code == 200
    assert read_response.status_code == 200
    assert read_response.json() == {"status": "ok"}
    assert send_response.json() == {
        "id": "msg-1",
        "chat_id": "chat-1",
        "sender_id": "agent-1",
        "content": "hello",
    }
    assert seen == [
        ("resolve_display_user", "user-1"),
        (
            "send",
            {
                "chat_id": "chat-1",
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
        ),
        ("mark_read", {"chat_id": "chat-1", "user_id": "agent-1"}),
    ]
