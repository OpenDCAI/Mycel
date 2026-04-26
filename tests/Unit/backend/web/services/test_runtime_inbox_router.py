from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.chat.api.http.runtime_inbox_router import drain_runtime_inbox_items


def test_drain_runtime_inbox_items_returns_metadata_and_clears_external_queue() -> None:
    drained_keys: list[str] = []
    queue_manager = SimpleNamespace(
        drain_all=lambda key: (
            drained_keys.append(key)
            or [
                SimpleNamespace(
                    content='{"event_type":"chat.message","chat_id":"chat-1","sender_name":"Human","summary":"New message"}',
                    notification_type="chat",
                    source="external",
                    sender_id="human-user-1",
                    sender_name="Human",
                )
            ]
        )
    )

    result = drain_runtime_inbox_items("external-user-1", queue_manager)

    assert drained_keys == ["external:external-user-1"]
    assert result == [
        {
            "event_type": "chat.message",
            "chat_id": "chat-1",
            "sender_name": "Human",
            "summary": "New message",
            "notification_type": "chat",
            "source": "external",
            "sender_id": "human-user-1",
        }
    ]


def test_drain_runtime_inbox_items_fails_loudly_on_invalid_payload() -> None:
    queue_manager = SimpleNamespace(
        drain_all=lambda _key: [
            SimpleNamespace(
                content="not-json",
                notification_type="chat",
                source="external",
                sender_id=None,
                sender_name=None,
            )
        ]
    )

    with pytest.raises(RuntimeError, match="Invalid external runtime inbox payload"):
        drain_runtime_inbox_items("external-user-1", queue_manager)
