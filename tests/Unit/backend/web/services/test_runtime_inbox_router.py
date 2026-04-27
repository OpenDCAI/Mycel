from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest

from backend.chat.api.http.runtime_inbox_router import (
    drain_runtime_inbox_items,
    wait_runtime_inbox,
    wait_runtime_inbox_items,
)


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


def test_wait_runtime_inbox_items_returns_after_external_queue_wake() -> None:
    queued: list[SimpleNamespace] = []
    registered: dict[str, object] = {}

    def _drain_all(key: str) -> list[SimpleNamespace]:
        assert key == "external:external-user-1"
        items = list(queued)
        queued.clear()
        return items

    def _register_wake(key: str, handler) -> None:
        assert key == "external:external-user-1"
        registered["handler"] = handler

    def _unregister_wake(key: str) -> None:
        assert key == "external:external-user-1"
        registered["unregistered"] = True

    queue_manager = SimpleNamespace(
        drain_all=_drain_all,
        register_wake=_register_wake,
        unregister_wake=_unregister_wake,
    )

    result_holder: dict[str, list[dict[str, object]]] = {}
    worker = threading.Thread(
        target=lambda: result_holder.update(
            items=wait_runtime_inbox_items(
                "external-user-1",
                queue_manager,
                timeout_seconds=1.0,
            )
        )
    )

    worker.start()
    while "handler" not in registered:
        pass
    queued.append(
        SimpleNamespace(
            content='{"event_type":"chat.message","chat_id":"chat-1"}',
            notification_type="chat",
            source="external",
            sender_id="human-user-1",
            sender_name="Human",
        )
    )
    registered["handler"](queued[0])
    worker.join(timeout=1.0)

    assert not worker.is_alive()
    assert registered["unregistered"] is True
    assert result_holder["items"] == [
        {
            "event_type": "chat.message",
            "chat_id": "chat-1",
            "notification_type": "chat",
            "source": "external",
            "sender_id": "human-user-1",
            "sender_name": "Human",
        }
    ]


@pytest.mark.asyncio
async def test_wait_runtime_inbox_endpoint_returns_count_and_notifications() -> None:
    queue_manager = SimpleNamespace(
        drain_all=lambda _key: [],
        register_wake=lambda _key, _handler: None,
        unregister_wake=lambda _key: None,
    )
    app = SimpleNamespace(state=SimpleNamespace(threads_runtime_state=SimpleNamespace(queue_manager=queue_manager)))

    result = await wait_runtime_inbox(
        app,
        "external-user-1",
        timeout_seconds=0.0,
    )

    assert result == {"count": 0, "notifications": []}
