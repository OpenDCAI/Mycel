from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from backend.web.services.event_buffer import ThreadEventBuffer
from backend.web.services.streaming_service import _resolve_run_event_repo, _run_agent_to_buffer, write_cancellation_markers
from core.runtime.middleware.monitor import AgentState
from eval.models import RunTrajectory


class _FakeDisplayBuilder:
    def apply_event(self, thread_id: str, event_type: str, data: dict) -> None:
        return None


class _FakeRuntime:
    def __init__(self) -> None:
        self.current_state = AgentState.ACTIVE
        self.current_run_source = None
        self.state = SimpleNamespace(flags=SimpleNamespace(is_compacting=False))
        self._event_callback = None

    def set_event_callback(self, cb) -> None:
        self._event_callback = cb

    def get_status_dict(self) -> dict[str, object]:
        return {"state": {"state": "idle", "flags": {}}, "calls": 0}

    def transition(self, new_state) -> bool:
        self.current_state = new_state
        return True


class _FakeGraphAgent:
    def __init__(self, *, expected_run_id: str, error: Exception | None = None, wait_forever: bool = False) -> None:
        self.expected_run_id = expected_run_id
        self.error = error
        self.wait_forever = wait_forever

    async def aget_state(self, _config):
        return SimpleNamespace(values={"messages": []})

    async def astream(self, *_args, **_kwargs):
        assert _FakeTrajectoryStore.header_calls == [
            {
                "run_id": self.expected_run_id,
                "thread_id": "thread-1",
                "started_at": "2026-04-08T12:00:00+00:00",
                "user_message": "hello",
                "status": "running",
            }
        ]
        if self.error is not None:
            raise self.error
        if self.wait_forever:
            await asyncio.Event().wait()
        if False:
            yield None


class _FakeTrajectoryStore:
    header_calls: list[dict] = []
    finalize_calls: list[dict] = []
    metric_calls: list[dict] = []

    def __init__(self) -> None:
        return None

    @classmethod
    def reset(cls) -> None:
        cls.header_calls = []
        cls.finalize_calls = []
        cls.metric_calls = []

    def upsert_run_header(self, **payload) -> None:
        _FakeTrajectoryStore.header_calls.append(payload)

    def finalize_run(self, **payload) -> None:
        _FakeTrajectoryStore.finalize_calls.append(payload)

    def save_metrics(self, run_id: str, tier: str, metrics) -> None:
        _FakeTrajectoryStore.metric_calls.append({"run_id": run_id, "tier": tier, "metrics": metrics.model_dump()})


class _FakeTrajectoryTracer:
    def __init__(self, *, thread_id: str, user_message: str, run_id: str | None = None, cost_calculator=None, **_kwargs):
        self.thread_id = thread_id
        self.user_message = user_message
        self.run_id = run_id
        self._start_time = datetime.fromisoformat("2026-04-08T12:00:00+00:00").astimezone(UTC)

    def to_trajectory(self) -> RunTrajectory:
        return RunTrajectory(
            id=self.run_id or "missing-run-id",
            thread_id=self.thread_id,
            user_message=self.user_message,
            final_response="done",
            run_tree_json="{}",
            started_at="2026-04-08T12:00:00+00:00",
            finished_at="2026-04-08T12:01:00+00:00",
            status="completed",
        )

    def enrich_from_runtime(self, trajectory: RunTrajectory, runtime) -> None:
        return None


async def _noop_async(*_args, **_kwargs) -> None:
    return None


class _VersionedCheckpointSaver:
    def __init__(self) -> None:
        self.checkpoint = {
            "v": 1,
            "ts": "2026-04-10T00:00:00+00:00",
            "id": "checkpoint-1",
            "channel_values": {"messages": []},
            "channel_versions": {"messages": "00000000000000000000000000000001.1234567890123456"},
            "versions_seen": {},
            "pending_sends": [],
            "updated_channels": None,
        }
        self.metadata = {"step": 3}
        self.saved_checkpoint = None
        self.saved_metadata = None
        self.saved_versions = None

    async def aget_tuple(self, _config):
        return SimpleNamespace(checkpoint=self.checkpoint, metadata=self.metadata)

    def get_next_version(self, current: str | None, _channel) -> str:
        if current is None:
            current_v = 0
        else:
            current_v = int(str(current).split(".")[0])
        return f"{current_v + 1:032}.test"

    async def aput(self, _config, checkpoint, metadata, new_versions):
        self.saved_checkpoint = checkpoint
        self.saved_metadata = metadata
        self.saved_versions = new_versions


def _fake_storage_container() -> SimpleNamespace:
    return SimpleNamespace(run_event_repo=lambda: SimpleNamespace(close=lambda: None))


def _make_app() -> SimpleNamespace:
    return SimpleNamespace(
        state=SimpleNamespace(
            display_builder=_FakeDisplayBuilder(),
            thread_tasks={},
            thread_last_active={},
            typing_tracker=None,
            queue_manager=SimpleNamespace(peek=lambda _thread_id: False),
        )
    )


def _install_runtime_writer_test_doubles(monkeypatch: pytest.MonkeyPatch) -> None:
    seq = 0

    async def fake_append_event(thread_id, run_id, event, message_id=None, run_event_repo=None):
        nonlocal seq
        seq += 1
        return seq

    monkeypatch.setattr("backend.web.services.event_store.append_event", fake_append_event)
    monkeypatch.setattr("backend.web.services.streaming_service.cleanup_old_runs", _noop_async)
    monkeypatch.setattr("backend.web.services.streaming_service._ensure_thread_handlers", lambda *args, **kwargs: None)
    monkeypatch.setattr("backend.web.services.streaming_service._consume_followup_queue", _noop_async)
    monkeypatch.setattr("backend.web.services.streaming_service.write_cancellation_markers", _noop_async)
    monkeypatch.setattr("backend.web.services.streaming_service._persist_cancelled_run_input_if_missing", _noop_async)
    monkeypatch.setattr("backend.web.services.streaming_service._flush_cancelled_owner_steers", _noop_async)
    monkeypatch.setattr("eval.storage.TrajectoryStore", _FakeTrajectoryStore)
    monkeypatch.setattr("eval.tracer.TrajectoryTracer", _FakeTrajectoryTracer)


@pytest.mark.asyncio
async def test_run_agent_to_buffer_persists_running_then_completed_eval_row(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeTrajectoryStore.reset()
    _install_runtime_writer_test_doubles(monkeypatch)

    agent = SimpleNamespace(
        agent=_FakeGraphAgent(expected_run_id="run-123"),
        runtime=_FakeRuntime(),
        storage_container=_fake_storage_container(),
    )

    result = await _run_agent_to_buffer(
        agent,
        "thread-1",
        "hello",
        _make_app(),
        True,
        ThreadEventBuffer(),
        "run-123",
    )

    assert result == ""
    assert _FakeTrajectoryStore.finalize_calls == [
        {
            "run_id": "run-123",
            "finished_at": "2026-04-08T12:01:00+00:00",
            "final_response": "done",
            "status": "completed",
            "run_tree_json": "{}",
            "trajectory_json": '{"id":"run-123","thread_id":"thread-1","user_message":"hello","final_response":"done","llm_calls":[],"tool_calls":[],"run_tree_json":"{}","started_at":"2026-04-08T12:00:00+00:00","finished_at":"2026-04-08T12:01:00+00:00","status":"completed"}',
        }
    ]
    assert [call["tier"] for call in _FakeTrajectoryStore.metric_calls] == ["system", "objective"]


def test_resolve_run_event_repo_requires_storage_container_run_event_repo() -> None:
    agent = SimpleNamespace(
        agent=_FakeGraphAgent(expected_run_id="run-123"),
        runtime=_FakeRuntime(),
        storage_container=None,
    )

    with pytest.raises(RuntimeError, match="storage_container.run_event_repo"):
        _resolve_run_event_repo(agent)


@pytest.mark.asyncio
async def test_run_agent_to_buffer_finalizes_same_eval_row_on_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeTrajectoryStore.reset()
    _install_runtime_writer_test_doubles(monkeypatch)

    agent = SimpleNamespace(
        agent=_FakeGraphAgent(expected_run_id="run-123", error=RuntimeError("boom")),
        runtime=_FakeRuntime(),
        storage_container=_fake_storage_container(),
    )

    result = await _run_agent_to_buffer(
        agent,
        "thread-1",
        "hello",
        _make_app(),
        True,
        ThreadEventBuffer(),
        "run-123",
    )

    assert result == ""
    assert _FakeTrajectoryStore.finalize_calls[0]["run_id"] == "run-123"
    assert _FakeTrajectoryStore.finalize_calls[0]["status"] == "error"


@pytest.mark.asyncio
async def test_run_agent_to_buffer_finalizes_same_eval_row_on_cancel(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeTrajectoryStore.reset()
    _install_runtime_writer_test_doubles(monkeypatch)

    agent = SimpleNamespace(
        agent=_FakeGraphAgent(expected_run_id="run-123", wait_forever=True),
        runtime=_FakeRuntime(),
        storage_container=_fake_storage_container(),
    )

    task = asyncio.create_task(
        _run_agent_to_buffer(
            agent,
            "thread-1",
            "hello",
            _make_app(),
            True,
            ThreadEventBuffer(),
            "run-123",
        )
    )
    for _ in range(50):
        if _FakeTrajectoryStore.header_calls:
            break
        await asyncio.sleep(0)

    task.cancel()
    result = await task

    assert result == ""
    assert _FakeTrajectoryStore.finalize_calls[0]["run_id"] == "run-123"
    assert _FakeTrajectoryStore.finalize_calls[0]["status"] == "cancelled"


@pytest.mark.asyncio
async def test_write_cancellation_markers_advances_string_channel_versions() -> None:
    saver = _VersionedCheckpointSaver()
    agent = SimpleNamespace(agent=SimpleNamespace(checkpointer=saver))

    cancelled = await write_cancellation_markers(
        agent,
        {"configurable": {"thread_id": "thread-1"}},
        {"tc-1": {"name": "shell"}},
    )

    assert cancelled == ["tc-1"]
    assert saver.saved_versions == {"messages": "00000000000000000000000000000002.test"}
    assert saver.saved_checkpoint["channel_versions"]["messages"] == "00000000000000000000000000000002.test"
    message = saver.saved_checkpoint["channel_values"]["messages"][-1]
    assert message.tool_call_id == "tc-1"
    assert message.name == "shell"
