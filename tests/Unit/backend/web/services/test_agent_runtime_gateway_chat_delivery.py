from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from backend.threads.chat_adapters.bootstrap import build_agent_runtime_gateway
from protocols.agent_runtime import (
    AgentChatContext,
    AgentChatDeliveryEnvelope,
    AgentChatRecipient,
    AgentRuntimeActor,
    AgentRuntimeMessage,
)


def _app(
    *,
    threads: list[dict[str, Any]] | None = None,
    pool: dict[str, Any] | None = None,
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
                get_by_id=lambda thread_id: next((row for row in thread_rows if row["id"] == thread_id), None),
            ),
            agent_pool=pool or {},
            typing_tracker=SimpleNamespace(start_chat=lambda thread_id, chat_id, user_id: started.append((thread_id, chat_id, user_id))),
            queue_manager=SimpleNamespace(
                enqueue=lambda content, thread_id, notification_type, **meta: enqueued.append(
                    (content, thread_id, meta.get("sender_id"), meta.get("sender_name"))
                )
            ),
            thread_cwd={},
            thread_sandbox={},
            thread_tasks={},
            thread_locks={},
            thread_locks_guard=asyncio.Lock(),
        )
    )
    return app, started, unread_calls, enqueued


def _envelope(
    *,
    chat_id: str = "chat-1",
    signal: str | None = "ping",
    content: str = "hello",
    thread_id: str | None = "thread-1",
) -> AgentChatDeliveryEnvelope:
    return AgentChatDeliveryEnvelope(
        chat=AgentChatContext(chat_id=chat_id),
        sender=AgentRuntimeActor(user_id="human-user-1", user_type="human", display_name="Human"),
        recipient=AgentChatRecipient(agent_user_id="agent-user-1", runtime_source="mycel", thread_id=thread_id),
        message=AgentRuntimeMessage(content=content, signal=signal),
    )


@pytest.mark.asyncio
async def test_gateway_dispatch_chat_enqueues_notification(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_get_or_create_agent(_app, _sandbox_type: str, *, thread_id: str):
        return SimpleNamespace(id=f"agent-for-{thread_id}")

    monkeypatch.setattr("backend.threads.chat_adapters.bootstrap.get_or_create_agent", _fake_get_or_create_agent)
    monkeypatch.setattr("backend.threads.chat_adapters.bootstrap.resolve_thread_sandbox", lambda _app, _thread_id: "local")
    monkeypatch.setattr("backend.threads.chat_adapters.bootstrap._ensure_thread_handlers", lambda *_args, **_kwargs: None)
    app, started, unread_calls, enqueued = _app()

    result = await build_agent_runtime_gateway(app).dispatch_chat(_envelope())

    assert result.status == "accepted"
    assert result.thread_id == "thread-1"
    assert started == [("thread-1", "chat-1", "agent-user-1")]
    assert unread_calls == []
    assert enqueued == [("hello", "thread-1", "human-user-1", "Human")]


@pytest.mark.asyncio
async def test_gateway_dispatch_chat_raises_for_missing_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "backend.threads.chat_adapters.bootstrap.get_or_create_agent", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError)
    )
    app, started, unread_calls, enqueued = _app(threads=[])

    with pytest.raises(RuntimeError, match="Agent chat recipient has no runtime thread: agent-user-1"):
        await build_agent_runtime_gateway(app).dispatch_chat(_envelope(thread_id=None))

    assert started == []
    assert unread_calls == []
    assert enqueued == []
