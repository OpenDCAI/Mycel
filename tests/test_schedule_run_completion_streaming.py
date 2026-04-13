from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from backend.web.services import streaming_service
from backend.web.services.event_buffer import ThreadEventBuffer
from core.runtime.middleware.monitor import AgentState


class FakeGraphAgent:
    checkpointer = None

    async def aget_state(self, _config):
        return SimpleNamespace(values={})

    async def astream(self, *_args, **_kwargs):
        if False:  # pragma: no cover
            yield None


class FakeRuntime:
    current_state = AgentState.ACTIVE

    state = SimpleNamespace(flags=SimpleNamespace(is_compacting=False))

    def set_event_callback(self, _callback) -> None:
        return None

    def get_status_dict(self) -> dict[str, Any]:
        return {}

    def transition(self, state) -> bool:
        self.current_state = state
        return True


class FakeAgent:
    def __init__(self) -> None:
        self.agent = FakeGraphAgent()
        self.runtime = FakeRuntime()
        self.storage_container = None


class FakeQueueManager:
    def dequeue(self, _thread_id: str):
        return None


class FakeDisplayBuilder:
    def apply_event(self, *_args, **_kwargs):
        return None


@pytest.mark.asyncio
async def test_streaming_final_boundary_marks_schedule_run_succeeded(monkeypatch: pytest.MonkeyPatch) -> None:
    completions: list[dict] = []

    def fake_complete_schedule_run_from_runtime(schedule_run_id: str | None, **fields) -> None:
        completions.append({"schedule_run_id": schedule_run_id, **fields})

    async def fake_cleanup_old_runs(*_args, **_kwargs) -> int:
        return 0

    monkeypatch.setattr(
        streaming_service.schedule_run_completion_service, "complete_schedule_run_from_runtime", fake_complete_schedule_run_from_runtime
    )
    monkeypatch.setattr(streaming_service, "cleanup_old_runs", fake_cleanup_old_runs)

    app = SimpleNamespace(
        state=SimpleNamespace(
            display_builder=FakeDisplayBuilder(),
            thread_last_active={},
            thread_tasks={},
            queue_manager=FakeQueueManager(),
        )
    )

    await streaming_service._run_agent_to_buffer(
        FakeAgent(),
        "thread_1",
        "scheduled work",
        app,
        False,
        ThreadEventBuffer(),
        "runtime_run_1",
        {"source": "schedule", "schedule_run_id": "schedule_run_1"},
    )

    assert completions == [
        {
            "schedule_run_id": "schedule_run_1",
            "source": "schedule",
            "status": "succeeded",
            "runtime_run_id": "runtime_run_1",
            "thread_id": "thread_1",
            "error": None,
        }
    ]
