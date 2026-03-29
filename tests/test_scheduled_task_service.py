"""Tests for scheduled_tasks domain — thread-bound scheduled task storage + dispatch."""

import asyncio
import sqlite3
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from core.runtime.middleware.queue.manager import MessageQueueManager
from core.runtime.middleware.queue.middleware import SteeringMiddleware


@pytest.fixture
def scheduled_modules(tmp_path, monkeypatch):
    from backend.scheduled_tasks import runtime, service

    db_path = tmp_path / "scheduled.db"
    monkeypatch.setattr(service, "DB_PATH", db_path)
    return service, runtime


class TestScheduledTaskCrud:
    def test_create_get_list_update_delete_task(self, scheduled_modules):
        service, _runtime = scheduled_modules

        created = service.create_scheduled_task(
            thread_id="thread-123",
            name="daily sync",
            instruction="Summarize the latest repo status.",
            cron_expression="0 9 * * *",
        )

        assert created["id"]
        assert created["thread_id"] == "thread-123"
        assert created["name"] == "daily sync"
        assert created["instruction"] == "Summarize the latest repo status."
        assert created["cron_expression"] == "0 9 * * *"
        assert created["enabled"] == 1
        assert created["next_trigger_at"] > created["created_at"]

        fetched = service.get_scheduled_task(created["id"])
        assert fetched == created

        items = service.list_scheduled_tasks()
        assert [item["id"] for item in items] == [created["id"]]

        updated = service.update_scheduled_task(
            created["id"],
            name="weekday sync",
            enabled=0,
        )
        assert updated["name"] == "weekday sync"
        assert updated["enabled"] == 0

        assert service.delete_scheduled_task(created["id"]) is True
        assert service.get_scheduled_task(created["id"]) is None

    def test_create_rejects_empty_required_fields(self, scheduled_modules):
        service, _runtime = scheduled_modules

        with pytest.raises(ValueError, match="thread_id"):
            service.create_scheduled_task(
                thread_id="",
                name="x",
                instruction="do x",
                cron_expression="* * * * *",
            )

        with pytest.raises(ValueError, match="name"):
            service.create_scheduled_task(
                thread_id="thread-1",
                name="",
                instruction="do x",
                cron_expression="* * * * *",
            )

        with pytest.raises(ValueError, match="instruction"):
            service.create_scheduled_task(
                thread_id="thread-1",
                name="x",
                instruction="",
                cron_expression="* * * * *",
            )

        with pytest.raises(ValueError, match="cron_expression"):
            service.create_scheduled_task(
                thread_id="thread-1",
                name="x",
                instruction="do x",
                cron_expression="",
            )

    def test_update_rejects_empty_required_fields(self, scheduled_modules):
        service, _runtime = scheduled_modules

        created = service.create_scheduled_task(
            thread_id="thread-123",
            name="daily sync",
            instruction="Summarize the latest repo status.",
            cron_expression="0 9 * * *",
        )

        with pytest.raises(ValueError, match="thread_id"):
            service.update_scheduled_task(created["id"], thread_id="")

        with pytest.raises(ValueError, match="name"):
            service.update_scheduled_task(created["id"], name="")

        with pytest.raises(ValueError, match="instruction"):
            service.update_scheduled_task(created["id"], instruction="")

    def test_delete_task_also_deletes_runs(self, scheduled_modules):
        service, _runtime = scheduled_modules

        created = service.create_scheduled_task(
            thread_id="thread-123",
            name="daily sync",
            instruction="Summarize the latest repo status.",
            cron_expression="0 9 * * *",
        )
        run = service.create_scheduled_task_run(
            scheduled_task_id=created["id"],
            thread_id=created["thread_id"],
            status="queued",
        )

        assert service.get_scheduled_task_run(run["id"]) is not None

        assert service.delete_scheduled_task(created["id"]) is True
        assert service.get_scheduled_task_run(run["id"]) is None


class TestScheduledTaskRuns:
    def test_create_and_update_run(self, scheduled_modules):
        service, _runtime = scheduled_modules

        task = service.create_scheduled_task(
            thread_id="thread-xyz",
            name="nightly review",
            instruction="Review the latest failures.",
            cron_expression="0 2 * * *",
        )

        run = service.create_scheduled_task_run(
            scheduled_task_id=task["id"],
            thread_id=task["thread_id"],
            status="queued",
        )

        assert run["scheduled_task_id"] == task["id"]
        assert run["thread_id"] == "thread-xyz"
        assert run["status"] == "queued"
        assert run["dispatch_result"] is None
        assert run["thread_run_id"] == ""

        updated = service.update_scheduled_task_run(
            run["id"],
            status="dispatched",
            dispatch_result={"status": "started", "run_id": "run-123"},
            thread_run_id="run-123",
            started_at=123456789,
        )
        assert updated["status"] == "dispatched"
        assert updated["dispatch_result"] == {"status": "started", "run_id": "run-123"}
        assert updated["thread_run_id"] == "run-123"
        assert updated["started_at"] == 123456789

        runs = service.list_scheduled_task_runs(task["id"])
        assert [item["id"] for item in runs] == [run["id"]]

    def test_update_task_retries_transient_database_locked(self, scheduled_modules, monkeypatch):
        service, _runtime = scheduled_modules

        task = service.create_scheduled_task(
            thread_id="thread-xyz",
            name="nightly review",
            instruction="Review the latest failures.",
            cron_expression="0 2 * * *",
        )

        original_conn = service._conn
        lock_state = {"remaining": 1}

        class FlakyConnection:
            def __init__(self, conn):
                self._conn = conn

            def __enter__(self):
                self._conn.__enter__()
                return self

            def __exit__(self, exc_type, exc, tb):
                return self._conn.__exit__(exc_type, exc, tb)

            def execute(self, sql, params=()):
                if sql.startswith("UPDATE scheduled_tasks SET") and lock_state["remaining"] > 0:
                    lock_state["remaining"] -= 1
                    raise sqlite3.OperationalError("database is locked")
                return self._conn.execute(sql, params)

            def __getattr__(self, name):
                return getattr(self._conn, name)

        monkeypatch.setattr(service, "_conn", lambda: FlakyConnection(original_conn()))

        updated = service.update_scheduled_task(task["id"], name="nightly review v2")

        assert updated is not None
        assert updated["name"] == "nightly review v2"
        assert lock_state["remaining"] == 0

    def test_update_run_retries_transient_database_locked(self, scheduled_modules, monkeypatch):
        service, _runtime = scheduled_modules

        task = service.create_scheduled_task(
            thread_id="thread-xyz",
            name="nightly review",
            instruction="Review the latest failures.",
            cron_expression="0 2 * * *",
        )
        run = service.create_scheduled_task_run(
            scheduled_task_id=task["id"],
            thread_id=task["thread_id"],
            status="queued",
        )

        original_conn = service._conn
        lock_state = {"remaining": 1}

        class FlakyConnection:
            def __init__(self, conn):
                self._conn = conn

            def __enter__(self):
                self._conn.__enter__()
                return self

            def __exit__(self, exc_type, exc, tb):
                return self._conn.__exit__(exc_type, exc, tb)

            def execute(self, sql, params=()):
                if sql.startswith("UPDATE scheduled_task_runs SET") and lock_state["remaining"] > 0:
                    lock_state["remaining"] -= 1
                    raise sqlite3.OperationalError("database is locked")
                return self._conn.execute(sql, params)

            def __getattr__(self, name):
                return getattr(self._conn, name)

        monkeypatch.setattr(service, "_conn", lambda: FlakyConnection(original_conn()))

        updated = service.update_scheduled_task_run(
            run["id"],
            status="dispatched",
            thread_run_id="run-123",
        )

        assert updated is not None
        assert updated["status"] == "dispatched"
        assert updated["thread_run_id"] == "run-123"
        assert lock_state["remaining"] == 0


class TestScheduledTaskScheduler:
    @pytest.mark.asyncio
    async def test_start_checks_due_tasks_immediately(self, scheduled_modules):
        _service, runtime = scheduled_modules
        scheduler = runtime.ScheduledTaskScheduler(check_interval_sec=60)
        calls = {"count": 0}

        async def fake_check_due_tasks() -> list[dict]:
            calls["count"] += 1
            return []

        scheduler.check_due_tasks = fake_check_due_tasks  # type: ignore[method-assign]

        await scheduler.start()
        assert calls["count"] == 1
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_scheduler_loop_survives_unexpected_check_error(self, scheduled_modules):
        _service, runtime = scheduled_modules
        scheduler = runtime.ScheduledTaskScheduler(check_interval_sec=0.01)
        calls = {"count": 0}

        async def flaky_check_due_tasks() -> list[dict]:
            calls["count"] += 1
            if calls["count"] == 1:
                raise RuntimeError("boom")
            scheduler._running = False
            return []

        scheduler.check_due_tasks = flaky_check_due_tasks  # type: ignore[method-assign]

        await scheduler.start()
        await asyncio.sleep(0.05)
        assert calls["count"] >= 2
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_trigger_task_creates_run_and_updates_task(self, scheduled_modules):
        service, runtime = scheduled_modules
        events: list[tuple[str, str]] = []

        async def fake_dispatch(thread_id: str, instruction: str) -> dict:
            events.append((thread_id, instruction))
            return {"status": "started", "run_id": "run-abc"}

        scheduler = runtime.ScheduledTaskScheduler(dispatch_fn=fake_dispatch)
        task = service.create_scheduled_task(
            thread_id="thread-1",
            name="morning brief",
            instruction="Give me a morning brief.",
            cron_expression="*/5 * * * *",
        )

        before = int(time.time() * 1000)
        run = await scheduler.trigger_task(task["id"])

        assert events == [("thread-1", "Give me a morning brief.")]
        assert run["scheduled_task_id"] == task["id"]
        assert run["status"] == "dispatched"
        assert run["dispatch_result"] == {"status": "started", "run_id": "run-abc"}
        assert run["thread_run_id"] == "run-abc"
        assert run["started_at"] >= before

        updated_task = service.get_scheduled_task(task["id"])
        assert updated_task["last_triggered_at"] >= before
        assert updated_task["next_trigger_at"] >= updated_task["last_triggered_at"]

    @pytest.mark.asyncio
    async def test_trigger_task_keeps_run_queued_when_thread_is_busy(self, scheduled_modules):
        service, runtime = scheduled_modules

        async def fake_dispatch(thread_id: str, instruction: str) -> dict:
            return {"status": "injected", "routing": "steer", "thread_id": thread_id}

        scheduler = runtime.ScheduledTaskScheduler(dispatch_fn=fake_dispatch)
        task = service.create_scheduled_task(
            thread_id="thread-busy",
            name="busy task",
            instruction="Wait until current run finishes.",
            cron_expression="*/5 * * * *",
        )

        run = await scheduler.trigger_task(task["id"])

        assert run["status"] == "queued"
        assert run["dispatch_result"] == {"status": "injected", "routing": "steer", "thread_id": "thread-busy"}
        assert run["thread_run_id"] == ""

    @pytest.mark.asyncio
    async def test_trigger_failure_marks_run_failed(self, scheduled_modules):
        service, runtime = scheduled_modules

        async def fake_dispatch(thread_id: str, instruction: str) -> dict:
            raise RuntimeError("dispatch boom")

        scheduler = runtime.ScheduledTaskScheduler(dispatch_fn=fake_dispatch)
        task = service.create_scheduled_task(
            thread_id="thread-2",
            name="bad task",
            instruction="This will fail.",
            cron_expression="*/5 * * * *",
        )

        run = await scheduler.trigger_task(task["id"])

        assert run["status"] == "failed"
        assert "dispatch boom" in run["error"]
        assert run["dispatch_result"] is None

    def test_is_due_uses_last_triggered_at_and_enabled(self, scheduled_modules):
        service, runtime = scheduled_modules
        scheduler = runtime.ScheduledTaskScheduler(dispatch_fn=None)

        task = service.create_scheduled_task(
            thread_id="thread-3",
            name="every minute",
            instruction="ping",
            cron_expression="*/1 * * * *",
        )
        assert scheduler.is_due(task) is True

        now_ms = int(time.time() * 1000)
        task = service.update_scheduled_task(task["id"], last_triggered_at=now_ms)
        assert scheduler.is_due(task) is False

        task = service.update_scheduled_task(task["id"], enabled=0, last_triggered_at=0)
        assert scheduler.is_due(task) is False

    def test_mark_run_completed_and_failed_helpers(self, scheduled_modules):
        service, runtime = scheduled_modules

        task = service.create_scheduled_task(
            thread_id="thread-4",
            name="helper task",
            instruction="Run helper path.",
            cron_expression="*/5 * * * *",
        )
        run = service.create_scheduled_task_run(
            scheduled_task_id=task["id"],
            thread_id=task["thread_id"],
            status="dispatched",
            thread_run_id="run-helper",
        )

        completed = runtime.mark_run_completed(run["id"])
        assert completed["status"] == "completed"
        assert completed["completed_at"] > 0

        another = service.create_scheduled_task_run(
            scheduled_task_id=task["id"],
            thread_id=task["thread_id"],
            status="dispatched",
            thread_run_id="run-helper-2",
        )
        failed = runtime.mark_run_failed(another["id"], "boom")
        assert failed["status"] == "failed"
        assert failed["completed_at"] > 0
        assert failed["error"] == "boom"

    def test_finalize_from_message_metadata(self, scheduled_modules):
        service, runtime = scheduled_modules

        task = service.create_scheduled_task(
            thread_id="thread-6",
            name="metadata finalize",
            instruction="Finalize from metadata.",
            cron_expression="*/5 * * * *",
        )
        run = service.create_scheduled_task_run(
            scheduled_task_id=task["id"],
            thread_id=task["thread_id"],
            status="dispatched",
            thread_run_id="thread-run-finalize",
        )

        result = runtime.finalize_from_message_metadata(
            {"scheduled_task_run_id": run["id"]},
            error=None,
        )
        assert result["status"] == "completed"

        another = service.create_scheduled_task_run(
            scheduled_task_id=task["id"],
            thread_id=task["thread_id"],
            status="dispatched",
            thread_run_id="thread-run-finalize-2",
        )
        result = runtime.finalize_from_message_metadata(
            {"scheduled_task_run_id": another["id"]},
            error="cancelled",
        )
        assert result["status"] == "failed"
        assert result["error"] == "cancelled"

        assert runtime.finalize_from_message_metadata({}, error=None) is None

    @pytest.mark.asyncio
    async def test_trigger_task_passes_scheduled_run_metadata_to_thread_dispatch(self, scheduled_modules, monkeypatch):
        service, runtime = scheduled_modules
        captured: dict[str, object] = {}

        async def fake_route_message_to_brain(app, thread_id, content, source="owner", sender_name=None, sender_avatar_url=None, attachments=None, extra_metadata=None):
            captured["app"] = app
            captured["thread_id"] = thread_id
            captured["content"] = content
            captured["source"] = source
            captured["extra_metadata"] = extra_metadata
            return {"status": "started", "run_id": "thread-run-1"}

        import backend.web.services.message_routing as message_routing

        monkeypatch.setattr(message_routing, "route_message_to_brain", fake_route_message_to_brain)

        scheduler = runtime.ScheduledTaskScheduler(app=object())
        task = service.create_scheduled_task(
            thread_id="thread-5",
            name="metadata task",
            instruction="Dispatch with metadata.",
            cron_expression="*/5 * * * *",
        )

        run = await scheduler.trigger_task(task["id"])

        assert captured["thread_id"] == "thread-5"
        assert captured["content"] == "Dispatch with metadata."
        assert captured["source"] == "scheduled_task"
        assert captured["extra_metadata"] == {"scheduled_task_run_id": run["id"]}

    @pytest.mark.asyncio
    async def test_consume_followup_queue_preserves_scheduled_run_metadata(self, scheduled_modules, tmp_path):
        service, _runtime = scheduled_modules
        from backend.web.services.streaming_service import _consume_followup_queue

        task = service.create_scheduled_task(
            thread_id="thread-followup",
            name="followup task",
            instruction="Finish later.",
            cron_expression="*/5 * * * *",
        )
        run = service.create_scheduled_task_run(
            scheduled_task_id=task["id"],
            thread_id=task["thread_id"],
            status="queued",
        )

        queue_manager = MessageQueueManager(db_path=str(tmp_path / "queue.db"))
        queue_manager.enqueue(
            "Finish later.",
            "thread-followup",
            source="scheduled_task",
            extra_metadata={"scheduled_task_run_id": run["id"]},
        )
        app = SimpleNamespace(state=SimpleNamespace(queue_manager=queue_manager, thread_event_buffers={}, thread_tasks={}))
        runtime = MagicMock()
        runtime.transition.return_value = True
        agent = SimpleNamespace(runtime=runtime)

        with patch("backend.web.services.streaming_service.start_agent_run") as mock_start:
            mock_start.return_value = "run-followup"
            await _consume_followup_queue(agent, "thread-followup", app)

        assert mock_start.call_count == 1
        assert mock_start.call_args.kwargs["message_metadata"]["scheduled_task_run_id"] == run["id"]
        updated = service.get_scheduled_task_run(run["id"])
        assert updated is not None
        assert updated["status"] == "dispatched"
        assert updated["thread_run_id"] == "run-followup"
        assert updated["started_at"] > 0

    def test_steering_middleware_tracks_scheduled_run_ids_from_queue(self, scheduled_modules, tmp_path):
        service, _runtime = scheduled_modules

        task = service.create_scheduled_task(
            thread_id="thread-inline",
            name="inline task",
            instruction="Handle inline.",
            cron_expression="*/5 * * * *",
        )
        run = service.create_scheduled_task_run(
            scheduled_task_id=task["id"],
            thread_id=task["thread_id"],
            status="queued",
        )

        queue_manager = MessageQueueManager(db_path=str(tmp_path / "queue.db"))
        queue_manager.enqueue(
            "Handle inline.",
            "thread-inline",
            source="scheduled_task",
            extra_metadata={"scheduled_task_run_id": run["id"]},
        )

        fake_runtime = SimpleNamespace(
            current_scheduled_task_run_ids=set(),
            emit_activity_event=lambda event: None,
        )
        middleware = SteeringMiddleware(queue_manager, agent_runtime=fake_runtime)

        result = middleware.before_model(
            state={},
            runtime=None,
            config={"configurable": {"thread_id": "thread-inline", "run_id": "run-inline"}},
        )

        assert result is not None
        message = result["messages"][0]
        assert message.metadata["scheduled_task_run_id"] == run["id"]
        assert run["id"] in fake_runtime.current_scheduled_task_run_ids
        updated = service.get_scheduled_task_run(run["id"])
        assert updated is not None
        assert updated["status"] == "dispatched"
        assert updated["thread_run_id"] == "run-inline"
        assert updated["started_at"] > 0

    @pytest.mark.asyncio
    async def test_run_completion_finalizes_runtime_tracked_scheduled_runs(self, scheduled_modules, tmp_path):
        service, _runtime = scheduled_modules
        from backend.web.services.event_buffer import ThreadEventBuffer
        from backend.web.services.streaming_service import _run_agent_to_buffer

        task = service.create_scheduled_task(
            thread_id="thread-runtime-finalize",
            name="runtime finalize",
            instruction="Finalize inline scheduled work.",
            cron_expression="*/5 * * * *",
        )
        run = service.create_scheduled_task_run(
            scheduled_task_id=task["id"],
            thread_id=task["thread_id"],
            status="queued",
        )

        class FakeGraphAgent:
            checkpointer = None

            async def aget_state(self, _config):
                return SimpleNamespace(values={"messages": []})

            async def astream(self, *_args, **_kwargs):
                if False:
                    yield None

        class FakeRuntime:
            current_state = "IDLE"

            def __init__(self):
                self._activity_sink = None
                self.current_scheduled_task_run_ids = {run["id"]}

            def set_event_callback(self, _callback):
                return None

            def bind_thread(self, activity_sink):
                self._activity_sink = activity_sink

            def transition(self, _new_state):
                return True

            def get_status_dict(self):
                return {}

            def get_pending_subagent_events(self):
                return []

        agent = SimpleNamespace(
            agent=FakeGraphAgent(),
            runtime=FakeRuntime(),
            storage_container=None,
        )
        app = SimpleNamespace(
            state=SimpleNamespace(
                display_builder=SimpleNamespace(apply_event=lambda *_args, **_kwargs: None),
                queue_manager=MessageQueueManager(db_path=str(tmp_path / "queue.db")),
                thread_tasks={},
                thread_event_buffers={},
                subagent_buffers={},
                thread_last_active={},
                typing_tracker=None,
            )
        )

        await _run_agent_to_buffer(
            agent,
            task["thread_id"],
            "hello",
            app,
            False,
            ThreadEventBuffer(),
            "run-finalize",
        )

        updated = service.get_scheduled_task_run(run["id"])
        assert updated is not None
        assert updated["status"] == "completed"
