from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from backend.web.services import agent_pool, message_routing, streaming_service
from core.runtime.middleware.monitor import AgentState


class FakeRuntime:
    def __init__(self, state=AgentState.ACTIVE) -> None:
        self.current_state = state

    def transition(self, state) -> bool:
        if self.current_state == AgentState.ACTIVE:
            return False
        self.current_state = state
        return True


class FakeQueueManager:
    def __init__(self) -> None:
        self.enqueued: list[dict] = []

    def enqueue(self, content: str, thread_id: str, notification_type: str, **fields) -> None:
        self.enqueued.append({"content": content, "thread_id": thread_id, "notification_type": notification_type, **fields})


@pytest.mark.asyncio
async def test_require_new_run_rejects_active_thread_without_enqueue(monkeypatch: pytest.MonkeyPatch) -> None:
    app = SimpleNamespace(state=SimpleNamespace(queue_manager=FakeQueueManager()))
    agent = SimpleNamespace(runtime=FakeRuntime())

    async def fake_get_or_create_agent(_app, _sandbox_type, *, thread_id: str):
        assert thread_id == "thread_1"
        return agent

    monkeypatch.setattr(agent_pool, "resolve_thread_sandbox", lambda _app, _thread_id: "local")
    monkeypatch.setattr(agent_pool, "get_or_create_agent", fake_get_or_create_agent)

    with pytest.raises(message_routing.TargetThreadActiveError):
        await message_routing.route_message_to_brain(
            app,
            "thread_1",
            "scheduled work",
            source="schedule",
            require_new_run=True,
        )

    assert app.state.queue_manager.enqueued == []


@pytest.mark.asyncio
async def test_direct_start_merges_extra_message_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    app = SimpleNamespace(
        state=SimpleNamespace(
            queue_manager=FakeQueueManager(),
            thread_locks={},
            thread_locks_guard=asyncio.Lock(),
        )
    )
    agent = SimpleNamespace(runtime=FakeRuntime(AgentState.IDLE))
    started: dict = {}

    async def fake_get_or_create_agent(_app, _sandbox_type, *, thread_id: str):
        assert thread_id == "thread_1"
        return agent

    def fake_start_agent_run(_agent, thread_id: str, content: str, _app, message_metadata: dict):
        started.update({"thread_id": thread_id, "content": content, "message_metadata": message_metadata})
        return "runtime_run_1"

    monkeypatch.setattr(agent_pool, "resolve_thread_sandbox", lambda _app, _thread_id: "local")
    monkeypatch.setattr(agent_pool, "get_or_create_agent", fake_get_or_create_agent)
    monkeypatch.setattr(streaming_service, "start_agent_run", fake_start_agent_run)

    result = await message_routing.route_message_to_brain(
        app,
        "thread_1",
        "scheduled work",
        source="schedule",
        require_new_run=True,
        extra_message_metadata={"schedule_run_id": "schedule_run_1"},
    )

    assert result == {"status": "started", "routing": "direct", "run_id": "runtime_run_1", "thread_id": "thread_1"}
    assert started["message_metadata"] == {
        "source": "schedule",
        "sender_name": None,
        "sender_avatar_url": None,
        "schedule_run_id": "schedule_run_1",
    }
