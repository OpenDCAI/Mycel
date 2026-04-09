import inspect

import pytest

from backend.web.services import monitor_service


def test_monitor_service_no_longer_imports_storage_factory_or_sqlite_repos() -> None:
    source = inspect.getsource(monitor_service)

    assert "backend.web.core.storage_factory" not in source
    assert "storage.providers.sqlite.chat_session_repo" not in source
    assert "storage.providers.sqlite.lease_repo" not in source
    assert "storage.providers.sqlite.sandbox_monitor_repo" not in source
    assert "storage.runtime" in source


def test_runtime_health_snapshot_defaults_to_supabase_when_strategy_missing(monkeypatch) -> None:
    class FakeRepo:
        def count_rows(self, _tables):
            return {
                "chat_sessions": 0,
                "sandbox_leases": 0,
                "lease_events": 0,
            }

        def close(self):
            return None

    monkeypatch.delenv("LEON_STORAGE_STRATEGY", raising=False)
    monkeypatch.setattr(monitor_service, "make_sandbox_monitor_repo", lambda: FakeRepo())
    monkeypatch.setattr(monitor_service, "init_providers_and_managers", lambda: ({}, {}))
    monkeypatch.setattr(monitor_service, "load_all_sessions", lambda _managers: [])

    payload = monitor_service.runtime_health_snapshot()

    assert payload["db"]["strategy"] == "supabase"
    assert payload["db"]["counts"] == {
        "chat_sessions": 0,
        "sandbox_leases": 0,
        "lease_events": 0,
    }


def test_list_leases_exposes_semantic_groups_and_summary(monkeypatch):
    class FakeRepo:
        def query_leases(self):
            return [
                {
                    "lease_id": "lease-healthy",
                    "provider_name": "local",
                    "desired_state": "running",
                    "observed_state": "running",
                    "current_instance_id": "inst-1",
                    "last_error": None,
                    "updated_at": "2026-04-06T00:10:00",
                    "thread_id": "thread-1",
                },
                {
                    "lease_id": "lease-diverged",
                    "provider_name": "local",
                    "desired_state": "running",
                    "observed_state": "detached",
                    "current_instance_id": "inst-2",
                    "last_error": "drift",
                    "updated_at": "2026-04-06T00:11:00",
                    "thread_id": "thread-2",
                },
                {
                    "lease_id": "lease-orphan-diverged",
                    "provider_name": "local",
                    "desired_state": "running",
                    "observed_state": "detached",
                    "current_instance_id": "inst-3",
                    "last_error": None,
                    "updated_at": "2026-04-06T00:12:00",
                    "thread_id": None,
                },
                {
                    "lease_id": "lease-orphan",
                    "provider_name": "local",
                    "desired_state": "stopped",
                    "observed_state": "stopped",
                    "current_instance_id": "inst-4",
                    "last_error": None,
                    "updated_at": "2026-04-06T00:13:00",
                    "thread_id": None,
                },
            ]

        def close(self):
            return None

    monkeypatch.setattr(monitor_service, "make_sandbox_monitor_repo", lambda: FakeRepo())
    monkeypatch.setattr(
        monitor_service,
        "_hours_since",
        lambda iso_timestamp: {
            "2026-04-06T00:10:00": 0.5,
            "2026-04-06T00:11:00": 0.5,
            "2026-04-06T00:12:00": 10.0,
            "2026-04-06T00:13:00": 10.0,
        }.get(iso_timestamp),
    )

    payload = monitor_service.list_leases()

    assert payload["summary"] == {
        "total": 4,
        "healthy": 1,
        "diverged": 1,
        "orphan": 1,
        "orphan_diverged": 1,
    }
    assert [group["key"] for group in payload["groups"]] == [
        "orphan_diverged",
        "diverged",
        "orphan",
        "healthy",
    ]
    assert payload["triage"]["summary"] == {
        "total": 4,
        "active_drift": 1,
        "detached_residue": 0,
        "orphan_cleanup": 2,
        "healthy_capacity": 1,
    }
    assert [group["key"] for group in payload["triage"]["groups"]] == [
        "active_drift",
        "detached_residue",
        "orphan_cleanup",
        "healthy_capacity",
    ]
    by_id = {item["lease_id"]: item for item in payload["items"]}
    assert by_id["lease-healthy"]["semantics"]["category"] == "healthy"
    assert by_id["lease-healthy"]["triage"]["category"] == "healthy_capacity"
    assert by_id["lease-diverged"]["semantics"]["category"] == "diverged"
    assert by_id["lease-diverged"]["triage"]["category"] == "active_drift"
    assert by_id["lease-orphan-diverged"]["semantics"]["category"] == "orphan_diverged"
    assert by_id["lease-orphan-diverged"]["triage"]["category"] == "orphan_cleanup"
    assert by_id["lease-orphan"]["semantics"]["category"] == "orphan"
    assert by_id["lease-orphan"]["triage"]["category"] == "orphan_cleanup"


def test_list_leases_marks_old_detached_running_rows_as_detached_residue(monkeypatch):
    class FakeRepo:
        def query_leases(self):
            return [
                {
                    "lease_id": "lease-stale",
                    "provider_name": "local",
                    "desired_state": "running",
                    "observed_state": "detached",
                    "current_instance_id": "inst-9",
                    "last_error": None,
                    "updated_at": "2026-04-05T00:00:00",
                    "thread_id": "subagent-1234",
                }
            ]

        def close(self):
            return None

    monkeypatch.setattr(monitor_service, "make_sandbox_monitor_repo", lambda: FakeRepo())
    monkeypatch.setattr(monitor_service, "_hours_since", lambda _: 24.0)

    payload = monitor_service.list_leases()

    item = payload["items"][0]
    assert item["semantics"]["category"] == "diverged"
    assert item["triage"]["category"] == "detached_residue"
    assert payload["triage"]["summary"]["detached_residue"] == 1


def test_get_lease_falls_back_to_historical_session_rows(monkeypatch):
    class FakeRepo:
        def query_lease(self, lease_id):
            return None

        def query_lease_threads(self, lease_id):
            return []

        def query_lease_events(self, lease_id):
            return []

        def query_lease_sessions(self, lease_id):
            return [
                {
                    "chat_session_id": "sess-old",
                    "thread_id": "thread-historical",
                    "status": "closed",
                    "started_at": "2026-04-06T10:00:00",
                    "ended_at": "2026-04-06T10:05:00",
                    "close_reason": "expired",
                    "lease_id": lease_id,
                    "provider_name": None,
                    "desired_state": None,
                    "observed_state": None,
                    "current_instance_id": None,
                    "last_error": None,
                }
            ]

        def close(self):
            return None

    monkeypatch.setattr(monitor_service, "make_sandbox_monitor_repo", lambda: FakeRepo())

    payload = monitor_service.get_lease("lease-historical")

    assert payload["lease_id"] == "lease-historical"
    assert payload["info"]["provider"] == "unknown"
    assert payload["state"]["text"] == "destroyed"
    assert payload["related_threads"]["items"] == [{"thread_id": "thread-historical", "thread_url": "/thread/thread-historical"}]


def test_build_evaluation_operator_surface_flags_runner_exit_before_threads_materialize():
    payload = monitor_service.build_evaluation_operator_surface(
        status="provisional",
        notes=("runner=direct rc=1 sandbox=local run_dir=/tmp/eval stdout_log=/tmp/eval/out.log stderr_log=/tmp/eval/err.log"),
        score={
            "score_gate": "provisional",
            "publishable": False,
            "run_dir": "/tmp/eval",
            "manifest_path": "/tmp/eval/run_manifest.json",
            "eval_summary_path": None,
            "trace_summaries_path": None,
            "scored": False,
        },
        threads_total=0,
        threads_running=0,
        threads_done=0,
    )

    assert payload["status"] == "provisional"
    assert payload["kind"] == "bootstrap_failure"
    assert payload["tone"] == "danger"
    assert payload["headline"] == "Runner exited before evaluation threads materialized."
    assert "bootstrap failure" in payload["summary"]
    assert payload["facts"][-2:] == [
        {"label": "Runner", "value": "direct"},
        {"label": "Exit code", "value": "1"},
    ]
    artifact_labels = {item["label"] for item in payload["artifacts"]}
    assert artifact_labels == {
        "Run directory",
        "Run manifest",
        "STDOUT log",
        "STDERR log",
        "Eval summary",
        "Trace summaries",
    }
    assert payload["artifact_summary"] == {
        "present": 4,
        "missing": 2,
        "total": 6,
    }
    assert payload["artifacts"][0]["status"] == "present"
    assert payload["artifacts"][-1]["status"] == "missing"


def test_build_evaluation_operator_surface_marks_running_waiting_for_threads():
    payload = monitor_service.build_evaluation_operator_surface(
        status="running",
        notes="runner=direct rc=0",
        score={
            "score_gate": "provisional",
            "publishable": False,
            "run_dir": "/tmp/eval",
            "manifest_path": "/tmp/eval/run_manifest.json",
            "eval_summary_path": None,
            "trace_summaries_path": None,
            "scored": False,
        },
        threads_total=0,
        threads_running=2,
        threads_done=0,
    )

    assert payload["status"] == "running"
    assert payload["kind"] == "running_waiting_for_threads"
    assert payload["tone"] == "default"
    assert "actively running" in payload["headline"]
    assert payload["artifact_summary"]["present"] == 2


def test_build_evaluation_operator_surface_marks_completed_with_errors():
    payload = monitor_service.build_evaluation_operator_surface(
        status="completed_with_errors",
        notes="runner=direct rc=0",
        score={
            "score_gate": "final",
            "publishable": True,
            "run_dir": "/tmp/eval",
            "manifest_path": "/tmp/eval/run_manifest.json",
            "eval_summary_path": "/tmp/eval/eval_summary.json",
            "trace_summaries_path": "/tmp/eval/trace_summaries.jsonl",
            "scored": True,
            "error_instances": 2,
        },
        threads_total=10,
        threads_running=0,
        threads_done=10,
    )

    assert payload["status"] == "completed_with_errors"
    assert payload["kind"] == "completed_with_errors"
    assert payload["tone"] == "warning"
    assert "completed with recorded errors" in payload["headline"]
    assert payload["artifact_summary"] == {
        "present": 4,
        "missing": 2,
        "total": 6,
    }


def test_evaluation_unavailable_surface_stays_explicit():
    payload = monitor_service._evaluation_unavailable_surface()

    assert payload["status"] == "unavailable"
    assert payload["kind"] == "unavailable"
    assert payload["tone"] == "warning"
    assert payload["headline"] == "Evaluation operator truth is not wired in this runtime yet."
    assert payload["artifact_summary"] == {
        "present": 0,
        "missing": 0,
        "total": 0,
    }
    assert payload["raw_notes"] is None


def test_monitor_evaluation_truth_reports_idle_when_repo_has_no_runs(monkeypatch):
    class FakeStore:
        def list_runs(self, thread_id=None, limit=50):
            return []

    monkeypatch.setattr(monitor_service, "make_eval_store", lambda: FakeStore())

    payload = monitor_service.get_monitor_evaluation_truth()

    assert payload["status"] == "idle"
    assert payload["kind"] == "no_recorded_runs"
    assert payload["tone"] == "default"
    assert payload["headline"] == "No persisted evaluation runs are available yet."
    assert payload["artifact_summary"] == {
        "present": 0,
        "missing": 0,
        "total": 0,
    }
    assert payload["facts"] == [{"label": "Status", "value": "idle"}]
    assert payload["raw_notes"] is None


def test_monitor_evaluation_truth_uses_latest_persisted_eval_run(monkeypatch):
    class FakeStore:
        def list_runs(self, thread_id=None, limit=50):
            return [
                {
                    "id": "run-1",
                    "thread_id": "thread-eval",
                    "started_at": "2026-04-08T00:00:00Z",
                    "finished_at": "2026-04-08T00:03:00Z",
                    "status": "completed",
                    "user_message": "solve the eval task",
                }
            ]

        def get_metrics(self, run_id, tier=None):
            assert run_id == "run-1"
            return [
                {
                    "id": "metric-1",
                    "tier": "system",
                    "timestamp": "2026-04-08T00:03:01Z",
                    "metrics": {
                        "total_tokens": 123,
                        "llm_call_count": 3,
                        "tool_call_count": 2,
                    },
                },
                {
                    "id": "metric-2",
                    "tier": "objective",
                    "timestamp": "2026-04-08T00:03:02Z",
                    "metrics": {
                        "total_duration_ms": 4567.0,
                    },
                },
            ]

    monkeypatch.setattr(monitor_service, "make_eval_store", lambda: FakeStore())

    payload = monitor_service.get_monitor_evaluation_truth()

    assert payload["status"] == "completed"
    assert payload["kind"] == "completed_recorded"
    assert payload["tone"] == "success"
    assert payload["headline"] == "Latest persisted evaluation run completed successfully."
    facts = {(item["label"], item["value"]) for item in payload["facts"]}
    assert ("Run ID", "run-1") in facts
    assert ("Thread ID", "thread-eval") in facts
    assert ("Total tokens", "123") in facts
    assert ("LLM calls", "3") in facts
    assert ("Tool calls", "2") in facts
    assert ("Duration (ms)", "4567") in facts
    assert payload["artifact_summary"] == {
        "present": 0,
        "missing": 0,
        "total": 0,
    }
    assert payload["raw_notes"] is None


def test_monitor_evaluation_dashboard_summary_reduces_operator_truth():
    summary = monitor_service.build_monitor_evaluation_dashboard_summary(
        {
            "status": "running",
            "kind": "running_active",
            "tone": "default",
            "headline": "Evaluation is actively running.",
            "summary": "Long form summary that should not leak into dashboard shape.",
            "facts": [],
            "artifacts": [],
            "artifact_summary": {"present": 2, "missing": 1, "total": 3},
            "next_steps": [],
            "raw_notes": "runner=direct rc=0",
        }
    )

    assert summary == {
        "evaluations_running": 1,
        "latest_evaluation": {
            "status": "running",
            "kind": "running_active",
            "tone": "default",
            "headline": "Evaluation is actively running.",
        },
    }


@pytest.mark.asyncio
async def test_monitor_evaluation_truth_reads_live_running_row_from_same_persisted_source(monkeypatch, tmp_path):
    import asyncio
    from datetime import UTC, datetime
    from types import SimpleNamespace

    from backend.web.services.event_buffer import ThreadEventBuffer
    from backend.web.services.streaming_service import _run_agent_to_buffer
    from core.runtime.middleware.monitor import AgentState
    from eval.repo import SQLiteEvalRepo
    from eval.storage import TrajectoryStore

    class FakeDisplayBuilder:
        def apply_event(self, thread_id: str, event_type: str, data: dict) -> None:
            return None

    class FakeRuntime:
        def __init__(self) -> None:
            self.current_state = AgentState.ACTIVE
            self.current_run_source = None
            self.state = SimpleNamespace(flags=SimpleNamespace(is_compacting=False))

        def set_event_callback(self, cb) -> None:
            self._event_callback = cb

        def get_status_dict(self) -> dict[str, object]:
            return {"state": {"state": "idle", "flags": {}}, "calls": 0}

        def transition(self, new_state) -> bool:
            self.current_state = new_state
            return True

    class FakeGraphAgent:
        async def aget_state(self, _config):
            return SimpleNamespace(values={"messages": []})

        async def astream(self, *_args, **_kwargs):
            await asyncio.Event().wait()
            if False:
                yield None

    class FakeTrajectoryTracer:
        def __init__(self, *, thread_id: str, user_message: str, run_id: str | None = None, cost_calculator=None, **_kwargs):
            self.thread_id = thread_id
            self.user_message = user_message
            self.run_id = run_id
            self._start_time = datetime.fromisoformat("2026-04-08T12:00:00+00:00").astimezone(UTC)

        def to_trajectory(self):
            from eval.models import RunTrajectory

            return RunTrajectory(
                id=self.run_id or "missing-run-id",
                thread_id=self.thread_id,
                user_message=self.user_message,
                final_response="",
                run_tree_json="{}",
                started_at="2026-04-08T12:00:00+00:00",
                finished_at="2026-04-08T12:01:00+00:00",
                status="completed",
            )

        def enrich_from_runtime(self, trajectory, runtime) -> None:
            return None

    async def noop_async(*_args, **_kwargs) -> None:
        return None

    seq = 0

    async def fake_append_event(thread_id, run_id, event, message_id=None, run_event_repo=None):
        nonlocal seq
        seq += 1
        return seq

    repo = SQLiteEvalRepo(tmp_path / "eval.db")
    repo.ensure_schema()
    store = TrajectoryStore(eval_repo=repo)

    monkeypatch.setattr(monitor_service, "make_eval_store", lambda: store)
    monkeypatch.setattr("backend.web.services.event_store.append_event", fake_append_event)
    monkeypatch.setattr("backend.web.services.streaming_service.cleanup_old_runs", noop_async)
    monkeypatch.setattr("backend.web.services.streaming_service._ensure_thread_handlers", lambda *args, **kwargs: None)
    monkeypatch.setattr("backend.web.services.streaming_service._consume_followup_queue", noop_async)
    monkeypatch.setattr("backend.web.services.streaming_service.write_cancellation_markers", noop_async)
    monkeypatch.setattr("backend.web.services.streaming_service._persist_cancelled_run_input_if_missing", noop_async)
    monkeypatch.setattr("backend.web.services.streaming_service._flush_cancelled_owner_steers", noop_async)
    monkeypatch.setattr("eval.storage.TrajectoryStore", lambda: store)
    monkeypatch.setattr("eval.tracer.TrajectoryTracer", FakeTrajectoryTracer)

    app = SimpleNamespace(
        state=SimpleNamespace(
            display_builder=FakeDisplayBuilder(),
            thread_tasks={},
            thread_last_active={},
            typing_tracker=None,
            queue_manager=SimpleNamespace(peek=lambda _thread_id: False),
        )
    )
    agent = SimpleNamespace(
        agent=FakeGraphAgent(),
        runtime=FakeRuntime(),
        storage_container=None,
    )

    task = asyncio.create_task(
        _run_agent_to_buffer(
            agent,
            "thread-eval",
            "hello",
            app,
            True,
            ThreadEventBuffer(),
            "run-live",
        )
    )

    payload = None
    for _ in range(100):
        payload = monitor_service.get_monitor_evaluation_truth()
        if payload["status"] == "running":
            break
        await asyncio.sleep(0)

    assert payload is not None
    assert payload["status"] == "running"
    assert payload["kind"] == "running_recorded"
    facts = {(item["label"], item["value"]) for item in payload["facts"]}
    assert ("Run ID", "run-live") in facts
    assert ("Thread ID", "thread-eval") in facts

    task.cancel()
    result = await task
    assert result == ""


def test_cleanup_resource_leases_deletes_allowed_detached_residue(monkeypatch):
    rows = [
        {
            "lease_id": "lease-stale",
            "provider_name": "local",
            "desired_state": "running",
            "observed_state": "detached",
            "current_instance_id": None,
            "last_error": None,
            "updated_at": "2026-04-05T00:00:00",
            "thread_id": "subagent-1234",
        }
    ]

    class FakeMonitorRepo:
        def query_leases(self):
            return list(rows)

        def query_lease_sessions(self, lease_id):
            assert lease_id == "lease-stale"
            return [{"chat_session_id": "sess-old", "status": "closed"}]

        def close(self):
            return None

    class FakeLeaseRepo:
        def __init__(self):
            self.deleted = []

        def delete(self, lease_id):
            self.deleted.append(lease_id)
            rows[:] = [row for row in rows if row["lease_id"] != lease_id]

        def close(self):
            return None

    class FakeChatSessionRepo:
        def lease_has_running_command(self, lease_id):
            assert lease_id == "lease-stale"
            return False

        def close(self):
            return None

    lease_repo = FakeLeaseRepo()
    monkeypatch.setattr(monitor_service, "make_sandbox_monitor_repo", lambda: FakeMonitorRepo())
    monkeypatch.setattr(monitor_service, "make_lease_repo", lambda: lease_repo)
    monkeypatch.setattr(monitor_service, "make_chat_session_repo", lambda: FakeChatSessionRepo())
    monkeypatch.setattr(monitor_service, "init_providers_and_managers", lambda: ({}, {}))
    monkeypatch.setattr(monitor_service, "_hours_since", lambda _: 24.0)

    payload = monitor_service.cleanup_resource_leases(
        action="cleanup_residue",
        lease_ids=["lease-stale"],
        expected_category="detached_residue",
    )

    assert lease_repo.deleted == ["lease-stale"]
    assert payload["attempted"] == ["lease-stale"]
    assert payload["cleaned"] == [{"lease_id": "lease-stale", "category": "detached_residue"}]
    assert payload["skipped"] == []
    assert payload["errors"] == []
    assert payload["refreshed_summary"]["detached_residue"] == 0


def test_cleanup_resource_leases_reports_category_mismatch_without_deleting(monkeypatch):
    rows = [
        {
            "lease_id": "lease-live",
            "provider_name": "local",
            "desired_state": "running",
            "observed_state": "detached",
            "current_instance_id": "inst-live",
            "last_error": None,
            "updated_at": "2026-04-06T00:00:00",
            "thread_id": "thread-1",
        }
    ]

    class FakeMonitorRepo:
        def query_leases(self):
            return list(rows)

        def query_lease_sessions(self, lease_id):
            assert lease_id == "lease-live"
            return [{"chat_session_id": "sess-live", "status": "active"}]

        def close(self):
            return None

    class FakeLeaseRepo:
        def __init__(self):
            self.deleted = []

        def delete(self, lease_id):
            self.deleted.append(lease_id)

        def close(self):
            return None

    class FakeChatSessionRepo:
        def lease_has_running_command(self, lease_id):
            assert lease_id == "lease-live"
            return True

        def close(self):
            return None

    lease_repo = FakeLeaseRepo()
    monkeypatch.setattr(monitor_service, "make_sandbox_monitor_repo", lambda: FakeMonitorRepo())
    monkeypatch.setattr(monitor_service, "make_lease_repo", lambda: lease_repo)
    monkeypatch.setattr(monitor_service, "make_chat_session_repo", lambda: FakeChatSessionRepo())
    monkeypatch.setattr(monitor_service, "init_providers_and_managers", lambda: ({}, {}))
    monkeypatch.setattr(monitor_service, "_hours_since", lambda _: 0.5)

    payload = monitor_service.cleanup_resource_leases(
        action="cleanup_residue",
        lease_ids=["lease-live"],
        expected_category="detached_residue",
    )

    assert lease_repo.deleted == []
    assert payload["attempted"] == ["lease-live"]
    assert payload["cleaned"] == []
    assert payload["skipped"] == ["lease-live"]
    assert payload["errors"] == [
        {
            "lease_id": "lease-live",
            "reason": "category_mismatch",
            "expected_category": "detached_residue",
            "actual_category": "active_drift",
        }
    ]


def test_runtime_health_snapshot_reports_supabase_storage_contract(monkeypatch):
    class FakeRepo:
        def count_rows(self, table_names):
            return {name: idx + 1 for idx, name in enumerate(table_names)}

        def close(self):
            return None

    monkeypatch.setenv("LEON_STORAGE_STRATEGY", "supabase")
    monkeypatch.setenv("LEON_DB_SCHEMA", "staging")
    monkeypatch.setattr(monitor_service, "make_sandbox_monitor_repo", lambda: FakeRepo())
    monkeypatch.setattr(monitor_service, "init_providers_and_managers", lambda: ({}, {}))
    monkeypatch.setattr(monitor_service, "load_all_sessions", lambda _managers: [])

    payload = monitor_service.runtime_health_snapshot()

    assert payload["db"] == {
        "strategy": "supabase",
        "schema": "staging",
        "counts": {
            "chat_sessions": 1,
            "sandbox_leases": 2,
            "lease_events": 3,
        },
    }
    assert payload["sessions"] == {"total": 0, "providers": {}}


def test_runtime_health_snapshot_keeps_supabase_contract_when_strategy_missing(monkeypatch):
    class FakeRepo:
        def count_rows(self, _tables):
            return {
                "chat_sessions": 1,
                "sandbox_leases": 2,
                "lease_events": 3,
            }

        def close(self):
            return None

    monkeypatch.delenv("LEON_STORAGE_STRATEGY", raising=False)
    monkeypatch.setenv("LEON_DB_SCHEMA", "staging")
    monkeypatch.setattr(monitor_service, "make_sandbox_monitor_repo", lambda: FakeRepo())
    monkeypatch.setattr(monitor_service, "init_providers_and_managers", lambda: ({}, {}))
    monkeypatch.setattr(monitor_service, "load_all_sessions", lambda _managers: [])

    payload = monitor_service.runtime_health_snapshot()

    assert payload["db"] == {
        "strategy": "supabase",
        "schema": "staging",
        "counts": {
            "chat_sessions": 1,
            "sandbox_leases": 2,
            "lease_events": 3,
        },
    }


def test_runtime_health_snapshot_reports_sqlite_contract_under_explicit_sqlite(monkeypatch, tmp_path):
    class FakeRepo:
        def count_rows(self, _tables):
            return {
                "chat_sessions": 4,
                "sandbox_leases": 5,
                "lease_events": 6,
            }

        def close(self):
            return None

    db_path = tmp_path / "sandbox.db"
    db_path.write_text("")
    monkeypatch.setenv("LEON_STORAGE_STRATEGY", "sqlite")
    monkeypatch.setattr(monitor_service, "make_runtime_health_monitor_repo", lambda db_path=None: FakeRepo())
    monkeypatch.setattr(monitor_service, "resolve_role_db_path", lambda role: db_path)
    monkeypatch.setattr(monitor_service, "init_providers_and_managers", lambda: ({}, {}))
    monkeypatch.setattr(monitor_service, "load_all_sessions", lambda _managers: [])

    payload = monitor_service.runtime_health_snapshot()

    assert payload["db"] == {
        "path": str(db_path),
        "exists": True,
        "counts": {
            "chat_sessions": 4,
            "sandbox_leases": 5,
            "lease_events": 6,
        },
    }
