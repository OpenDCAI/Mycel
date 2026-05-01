from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.chat.api.http.runtime_inbox_router import (
    chat_runtime_notifications,
    drain_runtime_inbox,
    drain_runtime_inbox_items,
    wait_runtime_inbox,
    wait_runtime_inbox_items,
)
from backend.chat.api.http.runtime_inbox_router import (
    router as runtime_inbox_router,
)
from backend.chat.runtime_inbox_stream import RuntimeInboxStreamState
from core.runtime.middleware.queue.manager import MessageQueueManager


class _SharedRuntimeInboxWakeBus:
    def __init__(self) -> None:
        self.handlers = {}

    def register(self, inbox_id, handler) -> None:
        self.handlers[inbox_id] = handler

    def unregister(self, inbox_id) -> None:
        self.handlers.pop(inbox_id, None)

    def publish(self, inbox_id) -> None:
        handler = self.handlers.get(inbox_id)
        if handler:
            handler()


def test_drain_runtime_inbox_items_returns_non_chat_metadata_and_clears_external_queue() -> None:
    drained_keys: list[str] = []
    queue_manager = SimpleNamespace(
        drain_all=lambda key: (
            drained_keys.append(key)
            or [
                SimpleNamespace(
                    content='{"event_type":"relationship.requested","summary":"Human requested contact."}',
                    notification_type="relationship",
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
            "event_type": "relationship.requested",
            "summary": "Human requested contact.",
            "notification_type": "relationship",
            "source": "external",
            "sender_id": "human-user-1",
            "sender_name": "Human",
        }
    ]


def test_drain_runtime_inbox_items_replaces_queued_chat_tokens_with_unread_projection() -> None:
    queued = [
        SimpleNamespace(
            content='{"event_type":"chat.message","chat_id":"chat-2","summary":"stale token"}',
            notification_type="chat",
            source="external",
            sender_id="human-user-1",
            sender_name="Human",
        )
    ]

    def _drain_all(_key: str) -> list[SimpleNamespace]:
        items = list(queued)
        queued.clear()
        return items

    result = drain_runtime_inbox_items(
        "external-user-1",
        SimpleNamespace(drain_all=_drain_all),
        messaging_service=SimpleNamespace(
            list_chats_for_user=lambda _user_id: [
                {
                    "id": "chat-2",
                    "unread_count": 1,
                    "last_message": {"id": "msg-2", "seq": 7, "sender_name": "Human", "content": "must not leak"},
                }
            ]
        ),
    )

    assert result == [
        {
            "event_type": "chat.message",
            "notification_type": "chat",
            "chat_id": "chat-2",
            "message_id": "msg-2",
            "message_seq": 7,
            "sender_name": "Human",
            "unread_count": 1,
        }
    ]
    assert (
        drain_runtime_inbox_items(
            "external-user-1",
            SimpleNamespace(drain_all=_drain_all),
            messaging_service=SimpleNamespace(list_chats_for_user=lambda _user_id: []),
        )
        == []
    )


def test_drain_runtime_inbox_items_projects_unread_chat_after_wake_token_is_gone() -> None:
    queued = [
        SimpleNamespace(
            content='{"event_type":"chat.message","chat_id":"chat-2"}',
            notification_type="chat",
            source="external",
            sender_id="human-user-1",
            sender_name="Human",
        )
    ]

    def _drain_all(_key: str) -> list[SimpleNamespace]:
        items = list(queued)
        queued.clear()
        return items

    messaging_service = SimpleNamespace(
        list_chats_for_user=lambda _user_id: [
            {
                "id": "chat-2",
                "unread_count": 1,
                "last_message": {
                    "id": "msg-2",
                    "seq": 8,
                    "sender_name": "Human",
                    "content": "must not leak",
                },
            }
        ]
    )

    first = drain_runtime_inbox_items(
        "external-user-1",
        SimpleNamespace(drain_all=_drain_all),
        messaging_service=messaging_service,
    )
    second = drain_runtime_inbox_items(
        "external-user-1",
        SimpleNamespace(drain_all=_drain_all),
        messaging_service=messaging_service,
    )

    assert (
        first
        == second
        == [
            {
                "event_type": "chat.message",
                "notification_type": "chat",
                "chat_id": "chat-2",
                "message_id": "msg-2",
                "message_seq": 8,
                "sender_name": "Human",
                "unread_count": 1,
            }
        ]
    )


def test_drain_runtime_inbox_items_drops_chat_token_when_chat_is_already_read() -> None:
    queue_manager = SimpleNamespace(
        drain_all=lambda _key: [
            SimpleNamespace(
                content='{"event_type":"chat.message","chat_id":"chat-2"}',
                notification_type="chat",
                source="external",
                sender_id="human-user-1",
                sender_name="Human",
            )
        ]
    )

    result = drain_runtime_inbox_items(
        "external-user-1",
        queue_manager,
        messaging_service=SimpleNamespace(
            list_chats_for_user=lambda _user_id: [
                {
                    "id": "chat-2",
                    "unread_count": 0,
                    "last_message": {"sender_name": "Human", "content": "must not leak"},
                }
            ]
        ),
    )

    assert result == []


def test_chat_runtime_notifications_derive_from_unread_chat_projection() -> None:
    notifications = chat_runtime_notifications(
        "external-user-1",
        SimpleNamespace(
            list_chats_for_user=lambda _user_id: [
                {
                    "id": "chat-1",
                    "unread_count": 0,
                    "last_message": {"sender_name": "Read Sender", "content": "must not leak"},
                },
                {
                    "id": "chat-2",
                    "unread_count": 2,
                    "last_message": {"id": "msg-2", "seq": 9, "sender_name": "Unread Sender", "content": "must not leak"},
                },
            ]
        ),
        chat_ids={"chat-2"},
    )

    assert notifications == [
        {
            "event_type": "chat.message",
            "notification_type": "chat",
            "chat_id": "chat-2",
            "message_id": "msg-2",
            "message_seq": 9,
            "sender_name": "Unread Sender",
            "unread_count": 2,
        }
    ]
    assert "must not leak" not in str(notifications)


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
    assert result_holder["items"] == []


def test_wait_runtime_inbox_items_returns_derived_chat_notification_after_wake() -> None:
    queued: list[SimpleNamespace] = []
    registered: dict[str, object] = {}

    def _drain_all(_key: str) -> list[SimpleNamespace]:
        items = list(queued)
        queued.clear()
        return items

    queue_manager = SimpleNamespace(
        drain_all=_drain_all,
        register_wake=lambda _key, handler: registered.update(handler=handler),
        unregister_wake=lambda _key: registered.update(unregistered=True),
    )
    result_holder: dict[str, list[dict[str, object]]] = {}
    worker = threading.Thread(
        target=lambda: result_holder.update(
            items=wait_runtime_inbox_items(
                "external-user-1",
                queue_manager,
                timeout_seconds=1.0,
                messaging_service=SimpleNamespace(
                    list_chats_for_user=lambda _user_id: [
                        {
                            "id": "chat-2",
                            "unread_count": 1,
                            "last_message": {"id": "msg-2", "seq": 8, "sender_name": "Human", "content": "must not leak"},
                        }
                    ]
                ),
            )
        )
    )

    worker.start()
    while "handler" not in registered:
        pass
    queued.append(
        SimpleNamespace(
            content='{"event_type":"chat.message","chat_id":"chat-2"}',
            notification_type="chat",
            source="external",
            sender_id="human-user-1",
            sender_name="Human",
        )
    )
    registered["woken"] = True
    registered["handler"](queued[0])
    worker.join(timeout=1.0)

    assert result_holder["items"] == [
        {
            "event_type": "chat.message",
            "notification_type": "chat",
            "chat_id": "chat-2",
            "message_id": "msg-2",
            "message_seq": 8,
            "sender_name": "Human",
            "unread_count": 1,
        }
    ]
    assert registered["unregistered"] is True


def test_wait_runtime_inbox_items_uses_signal_bus_and_drains_durable_queue(tmp_path) -> None:
    db_path = str(tmp_path / "queue.db")
    waiter_queue = MessageQueueManager(db_path=db_path)
    sender_queue = MessageQueueManager(db_path=db_path)
    wake_bus = _SharedRuntimeInboxWakeBus()
    result_holder: dict[str, list[dict[str, object]]] = {}
    worker = threading.Thread(
        target=lambda: result_holder.update(
            items=wait_runtime_inbox_items(
                "external-user-1",
                waiter_queue,
                timeout_seconds=1.0,
                wake_bus=wake_bus,
            )
        )
    )

    worker.start()
    deadline = time.monotonic() + 1.0
    while "external:external-user-1" not in wake_bus.handlers and time.monotonic() < deadline:
        time.sleep(0.001)
    assert "external:external-user-1" in wake_bus.handlers
    sender_queue.enqueue(
        '{"event_type":"relationship.requested","summary":"Human requested contact."}',
        "external:external-user-1",
        notification_type="relationship",
        source="external",
        sender_id="human-user-1",
        sender_name="Human",
        wake=False,
    )
    wake_bus.publish("external:external-user-1")
    worker.join(timeout=1.0)

    assert not worker.is_alive()
    assert result_holder["items"] == [
        {
            "event_type": "relationship.requested",
            "summary": "Human requested contact.",
            "notification_type": "relationship",
            "source": "external",
            "sender_id": "human-user-1",
            "sender_name": "Human",
        }
    ]
    assert wake_bus.handlers == {}


@pytest.mark.asyncio
async def test_wait_runtime_inbox_endpoint_returns_count_and_notifications() -> None:
    queue_manager = SimpleNamespace(
        drain_all=lambda _key: [],
        register_wake=lambda _key, _handler: (_ for _ in ()).throw(AssertionError("runtime inbox endpoint should use wake bus")),
        unregister_wake=lambda _key: (_ for _ in ()).throw(AssertionError("runtime inbox endpoint should use wake bus")),
    )
    wake_events: list[tuple[str, str]] = []
    wake_bus = SimpleNamespace(
        register=lambda key, _handler: wake_events.append(("register", key)),
        unregister=lambda key: wake_events.append(("unregister", key)),
    )
    app = SimpleNamespace(
        state=SimpleNamespace(
            threads_runtime_state=SimpleNamespace(
                queue_manager=queue_manager,
                runtime_inbox_wake_bus=wake_bus,
                runtime_inbox_stream=RuntimeInboxStreamState(),
            ),
            chat_runtime_state=SimpleNamespace(messaging_service=SimpleNamespace(list_chats_for_user=lambda _user_id: [])),
        )
    )

    result = await wait_runtime_inbox(
        app,
        "external-user-1",
        timeout_seconds=0.0,
    )

    assert result == {"count": 0, "notifications": []}
    assert wake_events == [
        ("register", "external:external-user-1"),
        ("unregister", "external:external-user-1"),
    ]


@pytest.mark.asyncio
async def test_drain_runtime_inbox_endpoint_assigns_monotonic_seq() -> None:
    queue_manager = SimpleNamespace(
        drain_all=lambda _key: [
            SimpleNamespace(
                content='{"event_type":"relationship.requested","summary":"Human requested contact."}',
                notification_type="relationship",
                source="external",
                sender_id="human-user-1",
                sender_name="Human",
            )
        ]
    )
    app = SimpleNamespace(
        state=SimpleNamespace(
            threads_runtime_state=SimpleNamespace(
                queue_manager=queue_manager,
                runtime_inbox_wake_bus=SimpleNamespace(),
                runtime_inbox_stream=RuntimeInboxStreamState(),
            ),
            chat_runtime_state=SimpleNamespace(messaging_service=SimpleNamespace(list_chats_for_user=lambda _user_id: [])),
        )
    )

    result = await drain_runtime_inbox(app, "external-user-1")

    assert result["notifications"] == [
        {
            "seq": 1,
            "event_type": "relationship.requested",
            "summary": "Human requested contact.",
            "notification_type": "relationship",
            "source": "external",
            "sender_id": "human-user-1",
            "sender_name": "Human",
        }
    ]


def test_runtime_inbox_websocket_streams_metadata_frame_after_wake(tmp_path) -> None:
    app, queue_manager, wake_bus = _runtime_ws_test_app("external-user-1", tmp_path)

    with TestClient(app) as client:
        with client.websocket_connect("/api/runtime/inbox/subscribe", subprotocols=["bearer.tok-1"]) as websocket:
            _wait_for_wake_handler(wake_bus, "external:external-user-1")
            queue_manager.enqueue(
                '{"event_type":"relationship.requested","summary":"Human requested contact."}',
                "external:external-user-1",
                notification_type="relationship",
                source="external",
                sender_id="human-user-1",
                sender_name="Human",
                wake=False,
            )
            wake_bus.publish("external:external-user-1")

            frame = websocket.receive_json()

    assert frame == {
        "type": "notify",
        "seq": 1,
        "fingerprint": frame["fingerprint"],
        "ts": frame["ts"],
        "metadata": {
            "event_type": "relationship.requested",
            "summary": "Human requested contact.",
            "notification_type": "relationship",
            "source": "external",
            "sender_id": "human-user-1",
            "sender_name": "Human",
        },
    }
    assert "content" not in str(frame).lower()


def test_runtime_inbox_websocket_replays_after_resume(tmp_path) -> None:
    app, queue_manager, wake_bus = _runtime_ws_test_app("external-user-1", tmp_path)

    with TestClient(app) as client:
        with client.websocket_connect("/api/runtime/inbox/subscribe", subprotocols=["bearer.tok-1"]) as websocket:
            _wait_for_wake_handler(wake_bus, "external:external-user-1")
            queue_manager.enqueue(
                '{"event_type":"relationship.requested","summary":"Human requested contact."}',
                "external:external-user-1",
                notification_type="relationship",
                source="external",
                sender_id="human-user-1",
                sender_name="Human",
                wake=False,
            )
            wake_bus.publish("external:external-user-1")
            first = websocket.receive_json()

        with client.websocket_connect("/api/runtime/inbox/subscribe", subprotocols=["bearer.tok-1"]) as websocket:
            websocket.send_json({"type": "resume", "since_seq": 0})
            replay = websocket.receive_json()

    assert replay == first


def test_runtime_inbox_stream_reports_replay_overflow() -> None:
    stream = RuntimeInboxStreamState(replay_limit=1)

    stream.assign("external-user-1", [{"event_type": "relationship.one"}])
    stream.assign("external-user-1", [{"event_type": "relationship.two"}])

    assert stream.replay_since("external-user-1", 0) == [
        {
            "type": "replay_overflow",
            "since_seq": 0,
            "oldest_seq": 2,
        }
    ]


def _runtime_ws_test_app(user_id: str, tmp_path) -> tuple[FastAPI, MessageQueueManager, _SharedRuntimeInboxWakeBus]:
    app = FastAPI()
    queue_manager = MessageQueueManager(db_path=str(tmp_path / "queue.db"))
    wake_bus = _SharedRuntimeInboxWakeBus()
    app.state.auth_runtime_state = SimpleNamespace(
        auth_service=SimpleNamespace(verify_token=lambda token: {"user_id": user_id} if token == "tok-1" else None)
    )
    app.state.user_repo = SimpleNamespace(get_by_id=lambda seen: object() if seen == user_id else None)
    app.state.threads_runtime_state = SimpleNamespace(
        queue_manager=queue_manager,
        runtime_inbox_wake_bus=wake_bus,
        runtime_inbox_stream=RuntimeInboxStreamState(),
    )
    app.state.chat_runtime_state = SimpleNamespace(messaging_service=SimpleNamespace(list_chats_for_user=lambda _user_id: []))
    app.include_router(runtime_inbox_router)
    return app, queue_manager, wake_bus


def _wait_for_wake_handler(wake_bus: _SharedRuntimeInboxWakeBus, inbox_id: str) -> None:
    deadline = time.monotonic() + 1.0
    while inbox_id not in wake_bus.handlers and time.monotonic() < deadline:
        time.sleep(0.001)
    assert inbox_id in wake_bus.handlers
