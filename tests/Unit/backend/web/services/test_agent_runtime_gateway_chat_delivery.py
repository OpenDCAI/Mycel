from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from backend.protocols.agent_runtime import (
    AgentChatContext,
    AgentChatDeliveryEnvelope,
    AgentChatRecipient,
    AgentRuntimeActor,
    AgentRuntimeMessage,
)
from backend.web.services.agent_runtime_gateway import NativeAgentRuntimeGateway
from core.runtime.middleware.monitor import AgentState


def _app(
    *,
    threads: list[dict[str, Any]] | None = None,
    pool: dict[str, Any] | None = None,
    unread_count: int = 7,
) -> tuple[SimpleNamespace, list[tuple[str, str, str]], list[tuple[str, str]], list[tuple[str, str, str | None, str | None]]]:
    started: list[tuple[str, str, str]] = []
    unread_calls: list[tuple[str, str]] = []
    enqueued: list[tuple[str, str, str | None, str | None]] = []
    thread_rows = threads or [{"id": "thread-1", "agent_user_id": "agent-user-1", "is_main": True, "branch_index": 0}]
    default_thread = next((row for row in thread_rows if row.get("is_main")), thread_rows[0])

    app = SimpleNamespace(
        state=SimpleNamespace(
            thread_repo=SimpleNamespace(
                get_by_user_id=lambda uid: default_thread if uid == "agent-user-1" else None,
                list_by_agent_user=lambda uid: list(thread_rows) if uid == "agent-user-1" else [],
            ),
            agent_pool=pool or {},
            typing_tracker=SimpleNamespace(start_chat=lambda thread_id, chat_id, user_id: started.append((thread_id, chat_id, user_id))),
            messaging_service=SimpleNamespace(
                count_unread=lambda chat_id, user_id: unread_calls.append((chat_id, user_id)) or unread_count
            ),
            queue_manager=SimpleNamespace(
                enqueue=lambda content, thread_id, notification_type, **meta: enqueued.append(
                    (content, thread_id, meta.get("sender_id"), meta.get("sender_name"))
                )
            ),
        )
    )
    return app, started, unread_calls, enqueued


def _envelope(*, chat_id: str = "chat-1", signal: str | None = "ping") -> AgentChatDeliveryEnvelope:
    return AgentChatDeliveryEnvelope(
        chat=AgentChatContext(chat_id=chat_id),
        sender=AgentRuntimeActor(user_id="human-user-1", user_type="human", display_name="Human"),
        recipient=AgentChatRecipient(agent_user_id="agent-user-1", runtime_source="mycel"),
        message=AgentRuntimeMessage(content="hello", signal=signal),
    )


@pytest.mark.asyncio
async def test_gateway_dispatch_chat_enqueues_notification(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_get_or_create_agent(_app, _sandbox_type: str, *, thread_id: str):
        return SimpleNamespace(id=f"agent-for-{thread_id}")

    monkeypatch.setattr("backend.web.services.agent_pool.get_or_create_agent", _fake_get_or_create_agent)
    monkeypatch.setattr("backend.web.services.agent_pool.resolve_thread_sandbox", lambda _app, _thread_id: "local")
    monkeypatch.setattr("backend.web.services.streaming_service._ensure_thread_handlers", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "core.runtime.middleware.queue.formatters.format_chat_notification",
        lambda sender_name, chat_id, unread_count, signal=None: f"{sender_name}|{chat_id}|{unread_count}|{signal}",
    )
    app, started, unread_calls, enqueued = _app(unread_count=7)

    result = await NativeAgentRuntimeGateway(app).dispatch_chat(_envelope())

    assert result.status == "accepted"
    assert result.thread_id == "thread-1"
    assert started == [("thread-1", "chat-1", "agent-user-1")]
    assert unread_calls == [("chat-1", "agent-user-1")]
    assert enqueued == [("Human|chat-1|7|ping", "thread-1", "human-user-1", "Human")]


@pytest.mark.asyncio
async def test_gateway_dispatch_chat_raises_for_missing_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "backend.web.services.agent_pool.get_or_create_agent", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError)
    )
    app, started, unread_calls, enqueued = _app(threads=[])
    app.state.thread_repo = SimpleNamespace(get_by_user_id=lambda _uid: None, list_by_agent_user=lambda _uid: [])

    with pytest.raises(RuntimeError, match="Agent chat recipient has no runtime thread: agent-user-1"):
        await NativeAgentRuntimeGateway(app).dispatch_chat(_envelope())

    assert started == []
    assert unread_calls == []
    assert enqueued == []


@pytest.mark.asyncio
async def test_gateway_prefers_latest_live_child_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_get_or_create_agent(_app, _sandbox_type: str, *, thread_id: str):
        return SimpleNamespace(id=f"agent-for-{thread_id}")

    monkeypatch.setattr("backend.web.services.agent_pool.get_or_create_agent", _fake_get_or_create_agent)
    monkeypatch.setattr("backend.web.services.agent_pool.resolve_thread_sandbox", lambda _app, _thread_id: "local")
    monkeypatch.setattr("backend.web.services.streaming_service._ensure_thread_handlers", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "core.runtime.middleware.queue.formatters.format_chat_notification",
        lambda sender_name, chat_id, unread_count, signal=None: f"{sender_name}|{chat_id}|{unread_count}|{signal}",
    )
    app, started, _, enqueued = _app(
        threads=[
            {"id": "thread-main", "agent_user_id": "agent-user-1", "is_main": True, "branch_index": 0},
            {"id": "thread-child-old", "agent_user_id": "agent-user-1", "is_main": False, "branch_index": 1},
            {"id": "thread-child-fresh", "agent_user_id": "agent-user-1", "is_main": False, "branch_index": 2},
        ],
        pool={
            "thread-main:local": SimpleNamespace(runtime=SimpleNamespace(current_state=AgentState.ACTIVE)),
            "thread-child-old:local": SimpleNamespace(runtime=SimpleNamespace(current_state=AgentState.IDLE)),
            "thread-child-fresh:local": SimpleNamespace(runtime=SimpleNamespace(current_state=AgentState.READY)),
        },
        unread_count=1,
    )

    result = await NativeAgentRuntimeGateway(app).dispatch_chat(_envelope(chat_id="chat-5"))

    assert result.status == "accepted"
    assert result.thread_id == "thread-child-fresh"
    assert started == [("thread-child-fresh", "chat-5", "agent-user-1")]
    assert enqueued == [("Human|chat-5|1|ping", "thread-child-fresh", "human-user-1", "Human")]
