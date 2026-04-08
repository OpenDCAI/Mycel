from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from backend.web.core.dependencies import get_current_user_id, verify_thread_owner
from backend.web.routers import monitor
from backend.web.routers import threads as threads_router
from core.runtime.middleware.monitor import AgentState
from eval.models import LLMCallRecord, RunTrajectory, ToolCallRecord
from eval.repo import SQLiteEvalRepo
from eval.storage import TrajectoryStore
from storage.contracts import UserRow, UserType


class _FakeUserRepo:
    def __init__(self) -> None:
        self._users = {
            "member-1": UserRow(
                id="member-1",
                type=UserType.AGENT,
                display_name="Toad",
                owner_user_id="owner-1",
                agent_config_id="cfg-1",
                avatar="avatars/member-1.png",
                created_at=1.0,
            ),
            "owner-1": UserRow(
                id="owner-1",
                type=UserType.HUMAN,
                display_name="Owner",
                owner_user_id=None,
                created_at=1.0,
            ),
        }
        self._seq = {"member-1": 0}

    def get_by_id(self, user_id: str):
        return self._users.get(user_id)

    def increment_thread_seq(self, user_id: str) -> int:
        self._seq[user_id] += 1
        return self._seq[user_id]


class _FakeThreadRepo:
    def __init__(self) -> None:
        self.rows: dict[str, dict] = {}

    def get_by_id(self, thread_id: str):
        row = self.rows.get(thread_id)
        if row is None:
            return None
        return {"id": thread_id, **row}

    def get_default_thread(self, agent_user_id: str):
        for thread_id, row in self.rows.items():
            if row["agent_user_id"] == agent_user_id and row["is_main"]:
                return {"id": thread_id, **row}
        return None

    def get_next_branch_index(self, agent_user_id: str) -> int:
        indices = [row["branch_index"] for row in self.rows.values() if row["agent_user_id"] == agent_user_id]
        return max(indices, default=0) + 1

    def create(self, **kwargs):
        self.rows[kwargs["thread_id"]] = dict(kwargs)


class _FakeDisplayBuilder:
    def apply_event(self, thread_id: str, event_type: str, data: dict) -> None:
        return None


class _FakeQueueManager:
    def peek(self, _thread_id: str) -> bool:
        return False

    def drain_all(self, _thread_id: str) -> list[object]:
        return []

    def enqueue(self, *_args, **_kwargs) -> None:
        return None


class _FakeRuntime:
    def __init__(self) -> None:
        self.current_state = AgentState.IDLE
        self.current_run_source = None
        self.state = SimpleNamespace(flags=SimpleNamespace(is_compacting=False))
        self._event_callback = None

    def set_event_callback(self, cb) -> None:
        self._event_callback = cb

    def get_status_dict(self) -> dict[str, object]:
        return {"state": {"state": "idle", "flags": {}}, "calls": 1, "context": {"usage_percent": 0.0}}

    def transition(self, new_state) -> bool:
        self.current_state = new_state
        return True


class _FakeGraphAgent:
    async def aget_state(self, _config):
        return SimpleNamespace(values={"messages": []})

    async def astream(self, *_args, **_kwargs):
        if False:
            yield None


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
            llm_calls=[
                LLMCallRecord(
                    run_id=self.run_id or "missing-run-id",
                    model_name="gpt-5.4-mini",
                    input_tokens=7,
                    output_tokens=4,
                    total_tokens=11,
                    cost_usd=0.01,
                )
            ],
            tool_calls=[
                ToolCallRecord(
                    run_id=self.run_id or "missing-run-id",
                    tool_name="Read",
                    tool_call_id="tool-1",
                    duration_ms=12.0,
                    success=True,
                    args_summary="{}",
                    result_summary="ok",
                )
            ],
            run_tree_json="{}",
            started_at="2026-04-08T12:00:00+00:00",
            finished_at="2026-04-08T12:01:00+00:00",
            status="completed",
        )

    def enrich_from_runtime(self, trajectory: RunTrajectory, runtime) -> None:
        return None


async def _noop_async(*_args, **_kwargs) -> None:
    return None


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(threads_router.router)
    app.include_router(monitor.router)
    app.dependency_overrides[get_current_user_id] = lambda: "owner-1"
    app.dependency_overrides[verify_thread_owner] = lambda: "owner-1"
    app.state.user_repo = _FakeUserRepo()
    app.state.thread_repo = _FakeThreadRepo()
    app.state.thread_sandbox = {}
    app.state.thread_cwd = {}
    app.state.display_builder = _FakeDisplayBuilder()
    app.state.thread_event_buffers = {}
    app.state.thread_tasks = {}
    app.state.thread_last_active = {}
    app.state.thread_locks = {}
    app.state.thread_locks_guard = asyncio.Lock()
    app.state.queue_manager = _FakeQueueManager()
    app.state.typing_tracker = None
    app.state.agent_pool = {}
    return app


@pytest.mark.asyncio
async def test_public_thread_messages_enable_trajectory_persists_eval_truth_for_monitor(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    app = _build_app()
    agent = SimpleNamespace(agent=_FakeGraphAgent(), runtime=_FakeRuntime(), storage_container=None)
    repo = SQLiteEvalRepo(tmp_path / "eval.db")
    repo.ensure_schema()
    store = TrajectoryStore(eval_repo=repo)
    seq = 0

    async def fake_append_event(thread_id, run_id, event, message_id=None, run_event_repo=None):
        nonlocal seq
        seq += 1
        return seq

    monkeypatch.setattr(threads_router, "_validate_sandbox_provider_gate", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(threads_router, "_invalidate_resource_overview_cache", lambda: None)
    monkeypatch.setattr(threads_router, "save_last_successful_config", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(threads_router, "_create_thread_sandbox_resources", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(threads_router, "_validate_mount_capability_gate", _noop_async)
    monkeypatch.setattr("backend.web.services.agent_pool.get_or_create_agent", AsyncMock(return_value=agent))
    monkeypatch.setattr("backend.web.services.event_store.append_event", fake_append_event)
    monkeypatch.setattr("backend.web.services.streaming_service.cleanup_old_runs", _noop_async)
    monkeypatch.setattr("backend.web.services.streaming_service._ensure_thread_handlers", lambda *args, **kwargs: None)
    monkeypatch.setattr("backend.web.services.streaming_service._consume_followup_queue", _noop_async)
    monkeypatch.setattr("backend.web.services.streaming_service.write_cancellation_markers", _noop_async)
    monkeypatch.setattr("backend.web.services.streaming_service._persist_cancelled_run_input_if_missing", _noop_async)
    monkeypatch.setattr("backend.web.services.streaming_service._flush_cancelled_owner_steers", _noop_async)
    monkeypatch.setattr("eval.storage.TrajectoryStore", lambda: store)
    monkeypatch.setattr("backend.web.services.monitor_service.make_eval_store", lambda: store)
    monkeypatch.setattr("eval.tracer.TrajectoryTracer", _FakeTrajectoryTracer)
    monkeypatch.setattr(
        "backend.web.routers.monitor.get_monitor_resource_overview_snapshot",
        lambda: {
            "summary": {
                "snapshot_at": "2026-04-07T00:00:00Z",
                "last_refreshed_at": "2026-04-07T00:00:00Z",
                "refresh_status": "fresh",
                "running_sessions": 0,
                "active_providers": 0,
                "unavailable_providers": 0,
            }
        },
    )
    monkeypatch.setattr(
        "backend.web.services.monitor_service.runtime_health_snapshot",
        lambda: {
            "snapshot_at": "2026-04-07T00:00:00Z",
            "db": {"counts": {"chat_sessions": 0}},
            "sessions": {"total": 0},
        },
    )
    monkeypatch.setattr(
        "backend.web.services.monitor_service.list_leases",
        lambda: {"summary": {"total": 0, "diverged": 0, "orphan_diverged": 0, "orphan": 0, "healthy": 0}},
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create_response = await client.post("/api/threads", json={"agent_user_id": "member-1", "sandbox": "local"})
        assert create_response.status_code == 200
        thread_id = create_response.json()["thread_id"]

        send_response = await client.post(
            f"/api/threads/{thread_id}/messages",
            json={"message": "hello", "enable_trajectory": True},
        )
        assert send_response.status_code == 200
        assert send_response.json()["status"] == "started"

        run_id = ""
        for _ in range(100):
            runs = store.list_runs(limit=1)
            if runs:
                run_id = str(runs[0]["id"])
                if len(store.get_metrics(run_id)) == 2 and thread_id not in app.state.thread_tasks:
                    break
            await asyncio.sleep(0)

        assert run_id
        assert len(store.get_metrics(run_id)) == 2

        evaluation_response = await client.get("/api/monitor/evaluation")
        dashboard_response = await client.get("/api/monitor/dashboard")

    assert evaluation_response.status_code == 200
    evaluation_payload = evaluation_response.json()
    assert evaluation_payload["status"] == "completed"
    assert evaluation_payload["kind"] == "completed_recorded"
    facts = {(item["label"], item["value"]) for item in evaluation_payload["facts"]}
    assert ("Thread ID", thread_id) in facts
    assert ("Metric Tiers", "2") in facts
    assert ("Total tokens", "11") in facts

    assert dashboard_response.status_code == 200
    dashboard_payload = dashboard_response.json()
    assert dashboard_payload["workload"]["evaluations_running"] == 0
    assert dashboard_payload["latest_evaluation"] == {
        "status": "completed",
        "kind": "completed_recorded",
        "tone": "success",
        "headline": "Latest persisted evaluation run completed successfully.",
    }
