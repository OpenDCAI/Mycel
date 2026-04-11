import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.web.services import monitor_service


@pytest.fixture(autouse=True)
def _default_live_thread_ids(monkeypatch):
    monkeypatch.setattr(
        monitor_service,
        "_live_thread_ids",
        lambda thread_ids: {str(thread_id or "").strip() for thread_id in thread_ids if str(thread_id or "").strip()},
    )


@pytest.fixture(autouse=True)
def _default_eval_batch_service(monkeypatch):
    class FakeBatchService:
        def list_batch_runs_for_thread(self, _thread_id):
            return []

    monkeypatch.setattr(monitor_service, "make_eval_batch_service", lambda: FakeBatchService())


def _lease_row(**overrides):
    row = {
        "lease_id": "lease-1",
        "provider_name": "daytona",
        "desired_state": "running",
        "observed_state": "running",
        "updated_at": "2026-04-08T00:00:00Z",
        "current_instance_id": "runtime-1",
        "last_error": None,
    }
    row.update(overrides)
    return row


_MISSING = object()


class FakeLeaseRepo:
    def __init__(self, *, lease=None, threads=None, sessions=None, runtime_session_id="runtime-1", leases=None):
        self.lease = lease
        self.threads = threads or []
        self.sessions = sessions or []
        self.runtime_session_id = runtime_session_id
        self.leases = leases or []

    def query_lease(self, lease_id):
        if self.lease is _MISSING:
            return None
        return self.lease if self.lease is not None else _lease_row(lease_id=lease_id)

    def query_lease_threads(self, _lease_id):
        return self.threads

    def query_lease_sessions(self, _lease_id):
        return self.sessions

    def query_lease_instance_id(self, _lease_id):
        return self.runtime_session_id

    def query_leases(self):
        return self.leases

    def close(self):
        return None


def _use_monitor_repo(monkeypatch, repo):
    monkeypatch.setattr(monitor_service, "make_sandbox_monitor_repo", lambda: repo)


def _detached_lease(**overrides):
    return _lease_row(desired_state="running", observed_state="detached", **overrides)


def _cleanup_state(reason: str):
    return {
        "allowed": True,
        "recommended_action": "lease_cleanup",
        "reason": reason,
        "operation": None,
        "recent_operations": [],
    }


def _blocked_cleanup_state(reason: str):
    return {
        "allowed": False,
        "recommended_action": None,
        "reason": reason,
        "operation": None,
        "recent_operations": [],
    }


def _record_destroy(calls):
    def _destroy_sandbox_lease(*, lease_id: str, provider_name: str):
        calls.append((lease_id, provider_name))
        return {
            "ok": True,
            "action": "destroy",
            "lease_id": lease_id,
            "provider": provider_name,
            "mode": "manager_lease",
        }

    return _destroy_sandbox_lease


class FakeThreadRepo:
    def __init__(self, thread):
        self.thread = thread

    def get_by_id(self, thread_id):
        return {**self.thread, "id": self.thread.get("id", thread_id)}


class FakeMonitorThreadRepo:
    def __init__(self, *, summary=None, sessions=None):
        self.summary = summary
        self.sessions = sessions or []

    def query_thread_summary(self, _thread_id):
        return self.summary

    def query_thread_sessions(self, _thread_id):
        return self.sessions

    def close(self):
        return None


def _stub_thread_detail(monkeypatch, *, owner=None, trajectory=None):
    monkeypatch.setattr(
        monitor_service,
        "_thread_owners",
        lambda *_args, **_kwargs: {"thread-1": owner},
    )
    monkeypatch.setattr(
        "backend.web.services.monitor_trace_service.build_monitor_thread_trajectory",
        AsyncMock(return_value=trajectory or {"run_id": None, "conversation": [], "events": []}),
    )


def test_get_monitor_provider_detail_reads_current_resource_snapshot(monkeypatch):
    monkeypatch.setattr(
        monitor_service,
        "get_resource_overview_snapshot",
        lambda: {
            "providers": [
                {
                    "id": "daytona",
                    "name": "daytona",
                    "sessions": [
                        {"leaseId": "lease-1", "threadId": "thread-1", "runtimeSessionId": "runtime-1"},
                        {"leaseId": "lease-2", "threadId": "thread-2"},
                    ],
                }
            ]
        },
    )

    payload = monitor_service.get_monitor_provider_detail("daytona")

    assert payload["provider"]["id"] == "daytona"
    assert payload["lease_ids"] == ["lease-1", "lease-2"]
    assert payload["thread_ids"] == ["thread-1", "thread-2"]
    assert payload["runtime_session_ids"] == ["runtime-1"]


def test_monitor_evaluation_scenario_catalog_reads_yaml_scenarios(tmp_path, monkeypatch):
    scenario_dir = tmp_path / "scenarios"
    scenario_dir.mkdir()
    (scenario_dir / "hello.yaml").write_text(
        "\n".join(
            [
                "id: hello",
                "name: Hello Eval",
                "category: smoke",
                "sandbox: local",
                "messages:",
                "  - content: Say hello like a real assistant.",
            ]
        )
    )
    monkeypatch.setattr(monitor_service, "EVAL_SCENARIO_DIR", scenario_dir)

    payload = monitor_service.get_monitor_evaluation_scenarios()

    assert payload == {
        "items": [
            {
                "scenario_id": "hello",
                "name": "Hello Eval",
                "category": "smoke",
                "sandbox": "local",
                "message_count": 1,
                "timeout_seconds": 120,
            }
        ],
        "count": 1,
    }


def test_create_monitor_evaluation_batch_uses_batch_service(monkeypatch):
    calls = []

    class FakeBatchService:
        def create_batch(self, **kwargs):
            calls.append(kwargs)
            return {"batch_id": "batch-created", "status": "pending"}

    monkeypatch.setattr(monitor_service, "make_eval_batch_service", lambda: FakeBatchService())

    payload = monitor_service.create_monitor_evaluation_batch(
        submitted_by_user_id="owner-1",
        agent_user_id="agent-1",
        scenario_ids=["scenario-1"],
        sandbox="local",
        max_concurrent=1,
    )

    assert payload == {"batch": {"batch_id": "batch-created", "status": "pending"}}
    assert calls == [
        {
            "submitted_by_user_id": "owner-1",
            "agent_user_id": "agent-1",
            "scenario_ids": ["scenario-1"],
            "sandbox": "local",
            "max_concurrent": 1,
        }
    ]


def test_start_monitor_evaluation_batch_schedules_runner(tmp_path, monkeypatch):
    scenario_dir = tmp_path / "scenarios"
    scenario_dir.mkdir()
    (scenario_dir / "scenario-1.yaml").write_text(
        "\n".join(
            [
                "id: scenario-1",
                "name: Scenario 1",
                "sandbox: local",
                "messages:",
                "  - content: Solve a realistic task.",
            ]
        )
    )
    scheduled = []

    class FakeBatchService:
        def get_batch_detail(self, batch_id):
            return {
                "batch": {
                    "batch_id": batch_id,
                    "agent_user_id": "agent-1",
                    "config_json": {
                        "scenario_ids": ["scenario-1"],
                        "sandbox": "daytona_selfhost",
                    },
                },
                "runs": [],
            }

        def update_batch_status(self, batch_id, status):
            return {"batch_id": batch_id, "status": status}

    monkeypatch.setattr(monitor_service, "EVAL_SCENARIO_DIR", scenario_dir)
    monkeypatch.setattr(monitor_service, "make_eval_batch_service", lambda: FakeBatchService())

    payload = monitor_service.start_monitor_evaluation_batch(
        "batch-1",
        base_url="http://testserver",
        token="token-1",
        schedule_task=lambda fn, **kwargs: scheduled.append((fn, kwargs)),
    )

    assert payload == {"accepted": True, "batch": {"batch_id": "batch-1", "status": "running"}}
    assert len(scheduled) == 1
    assert scheduled[0][1]["base_url"] == "http://testserver"
    assert scheduled[0][1]["token"] == "token-1"
    assert scheduled[0][1]["agent_user_id"] == "agent-1"
    assert scheduled[0][1]["scenarios"][0].id == "scenario-1"
    assert scheduled[0][1]["scenarios"][0].sandbox == "daytona_selfhost"


def test_get_monitor_provider_detail_fails_loudly_when_provider_missing(monkeypatch):
    monkeypatch.setattr(monitor_service, "get_resource_overview_snapshot", lambda: {"providers": []})

    with pytest.raises(KeyError, match="Provider not found: ghost"):
        monitor_service.get_monitor_provider_detail("ghost")


def test_get_monitor_lease_detail_merges_monitor_repo_state(monkeypatch):
    _use_monitor_repo(
        monkeypatch,
        FakeLeaseRepo(
            threads=[{"thread_id": "thread-1"}],
            sessions=[{"chat_session_id": "session-1", "thread_id": "thread-1", "status": "active"}],
        ),
    )

    payload = monitor_service.get_monitor_lease_detail("lease-1")

    assert payload["lease"]["lease_id"] == "lease-1"
    assert payload["provider"] == {"id": "daytona", "name": "daytona"}
    assert payload["runtime"] == {"runtime_session_id": "runtime-1"}
    assert payload["threads"] == [{"thread_id": "thread-1"}]
    assert payload["sessions"] == [
        {
            "chat_session_id": "session-1",
            "thread_id": "thread-1",
            "status": "active",
            "started_at": None,
            "ended_at": None,
            "close_reason": None,
        }
    ]


def test_get_monitor_lease_detail_exposes_cleanup_state(monkeypatch):
    _use_monitor_repo(monkeypatch, FakeLeaseRepo(lease=_detached_lease()))

    payload = monitor_service.get_monitor_lease_detail("lease-1")

    assert payload["cleanup"] == _cleanup_state("Lease is orphan cleanup residue and can enter managed cleanup.")


@pytest.mark.parametrize("runtime_session_id", ["runtime-1", None])
def test_get_monitor_lease_detail_blocks_detached_residue_with_thread_binding(monkeypatch, runtime_session_id):
    _use_monitor_repo(
        monkeypatch,
        FakeLeaseRepo(
            lease=_detached_lease(current_instance_id=runtime_session_id),
            threads=[{"thread_id": "thread-historical"}],
            runtime_session_id=runtime_session_id,
        ),
    )

    payload = monitor_service.get_monitor_lease_detail("lease-1")

    assert payload["runtime"] == {"runtime_session_id": runtime_session_id}
    assert payload["triage"]["category"] == "detached_residue"
    assert payload["cleanup"] == _blocked_cleanup_state("Lease still has thread bindings and cannot enter managed cleanup.")


def test_get_monitor_lease_detail_ignores_stale_thread_refs_when_classifying_triage(monkeypatch):
    _use_monitor_repo(
        monkeypatch,
        FakeLeaseRepo(
            lease=_lease_row(desired_state="paused", observed_state="paused"),
            threads=[{"thread_id": "thread-gone"}],
        ),
    )
    monkeypatch.setattr(monitor_service, "_live_thread_ids", lambda thread_ids: set())

    payload = monitor_service.get_monitor_lease_detail("lease-1")

    assert payload["threads"] == []
    assert payload["triage"]["category"] == "orphan_cleanup"
    assert payload["cleanup"] == _cleanup_state("Lease is orphan cleanup residue and can enter managed cleanup.")


@pytest.mark.parametrize("runtime_session_id", ["runtime-1", None])
def test_request_monitor_lease_cleanup_rejects_detached_residue_with_thread_binding(monkeypatch, runtime_session_id):
    calls: list[tuple[str, str]] = []
    _use_monitor_repo(
        monkeypatch,
        FakeLeaseRepo(
            lease=_detached_lease(current_instance_id=runtime_session_id),
            threads=[{"thread_id": "thread-historical"}],
            runtime_session_id=runtime_session_id,
        ),
    )
    monkeypatch.setattr(
        "backend.web.services.sandbox_service.destroy_sandbox_lease",
        _record_destroy(calls),
        raising=False,
    )

    payload = monitor_service.request_monitor_lease_cleanup("lease-1")

    assert payload["accepted"] is False
    assert payload["message"] == "Lease still has thread bindings and cannot enter managed cleanup."
    assert payload["operation"] is None
    assert calls == []


def test_get_monitor_lease_detail_fails_loudly_when_lease_missing(monkeypatch):
    _use_monitor_repo(monkeypatch, FakeLeaseRepo(lease=_MISSING))

    with pytest.raises(KeyError, match="Lease not found: lease-404"):
        monitor_service.get_monitor_lease_detail("lease-404")


def test_list_leases_ignores_stale_thread_refs_when_classifying_triage(monkeypatch):
    _use_monitor_repo(
        monkeypatch,
        FakeLeaseRepo(leases=[_lease_row(desired_state="paused", observed_state="paused", thread_id="thread-gone")]),
    )
    monkeypatch.setattr(monitor_service, "_live_thread_ids", lambda thread_ids: set())

    payload = monitor_service.list_leases()

    assert payload["triage"]["summary"]["orphan_cleanup"] == 1
    assert payload["triage"]["summary"]["healthy_capacity"] == 0
    assert payload["items"][0]["thread"] == {"thread_id": None, "is_orphan": True}
    assert payload["items"][0]["triage"]["category"] == "orphan_cleanup"


@pytest.mark.asyncio
async def test_get_monitor_thread_detail_exposes_trajectory_state(monkeypatch):
    _use_monitor_repo(
        monkeypatch,
        FakeMonitorThreadRepo(
            summary={
                "provider_name": "daytona",
                "lease_id": "lease-1",
                "current_instance_id": "runtime-1",
                "desired_state": "running",
                "observed_state": "running",
            },
            sessions=[{"chat_session_id": "session-1", "status": "active"}],
        ),
    )
    _stub_thread_detail(
        monkeypatch,
        owner={"user_id": "user-1", "display_name": "Ada", "email": "ada@example.com"},
        trajectory={
            "run_id": "run-1",
            "conversation": [
                {"role": "human", "text": "Please inspect the sandbox drift."},
                {"role": "tool_call", "tool": "terminal", "args": "{'cmd': 'pwd'}"},
                {"role": "tool_result", "tool": "terminal", "text": "/workspace"},
                {"role": "assistant", "text": "The sandbox is healthy now."},
            ],
            "events": [
                {"seq": 1, "event_type": "tool_call", "actor": "tool", "summary": "terminal"},
                {"seq": 2, "event_type": "status", "actor": "runtime", "summary": "state=active calls=1"},
            ],
        },
    )
    app = SimpleNamespace(
        state=SimpleNamespace(
            thread_repo=FakeThreadRepo(
                {"id": "thread-1", "thread_id": "thread-1", "title": "Investigate sandbox drift", "status": "active"}
            ),
            user_repo=object(),
        )
    )

    payload = await monitor_service.get_monitor_thread_detail(app, "thread-1")

    assert payload["thread"]["thread_id"] == "thread-1"
    assert payload["owner"]["display_name"] == "Ada"
    assert payload["trajectory"]["run_id"] == "run-1"
    assert payload["trajectory"]["conversation"][0]["role"] == "human"
    assert payload["trajectory"]["events"][0]["event_type"] == "tool_call"


def test_monitor_detail_contracts_do_not_create_resource_cache_import_cycle():
    result = subprocess.run(
        [sys.executable, "-c", "import backend.web.main"],
        capture_output=True,
        text=True,
        cwd=".",
    )

    assert result.returncode == 0, result.stderr


@pytest.mark.asyncio
async def test_get_monitor_thread_detail_derives_summary_from_session_state_when_repo_summary_missing(monkeypatch):
    _use_monitor_repo(
        monkeypatch,
        FakeMonitorThreadRepo(
            sessions=[
                {
                    "chat_session_id": "sess-1",
                    "status": "closed",
                    "lease_id": "lease-1",
                    "provider_name": "daytona",
                    "desired_state": "paused",
                    "observed_state": "paused",
                    "current_instance_id": "runtime-1",
                    "started_at": "2026-04-08T00:00:00Z",
                    "ended_at": "2026-04-08T01:00:00Z",
                    "close_reason": "expired",
                }
            ]
        ),
    )
    _stub_thread_detail(monkeypatch, owner={"agent_user_id": "agent-1", "agent_name": "Toad"})
    app = SimpleNamespace(state=SimpleNamespace(thread_repo=FakeThreadRepo({"status": "active"}), user_repo=None))

    payload = await monitor_service.get_monitor_thread_detail(app, "thread-1")

    assert payload["summary"] == {
        "provider_name": "daytona",
        "lease_id": "lease-1",
        "current_instance_id": "runtime-1",
        "desired_state": "paused",
        "observed_state": "paused",
    }


@pytest.mark.asyncio
async def test_get_monitor_thread_detail_normalizes_owner_shape_for_frontend(monkeypatch):
    _use_monitor_repo(monkeypatch, FakeMonitorThreadRepo())
    _stub_thread_detail(
        monkeypatch,
        owner={"agent_user_id": "agent-1", "agent_name": "Toad", "avatar_url": "/api/users/agent-1/avatar"},
    )
    app = SimpleNamespace(state=SimpleNamespace(thread_repo=FakeThreadRepo({"status": "active"}), user_repo=None))

    payload = await monitor_service.get_monitor_thread_detail(app, "thread-1")

    assert payload["owner"] == {
        "user_id": "agent-1",
        "display_name": "Toad",
        "email": None,
        "avatar_url": "/api/users/agent-1/avatar",
    }


@pytest.mark.asyncio
async def test_get_monitor_thread_detail_normalizes_thread_shape_for_frontend(monkeypatch):
    _use_monitor_repo(monkeypatch, FakeMonitorThreadRepo())
    _stub_thread_detail(monkeypatch, owner=None)
    app = SimpleNamespace(
        state=SimpleNamespace(
            thread_repo=FakeThreadRepo({"id": "thread-1", "title": "Investigate drift", "status": "active"}),
            user_repo=None,
        )
    )

    payload = await monitor_service.get_monitor_thread_detail(app, "thread-1")

    assert payload["thread"] == {
        "id": "thread-1",
        "thread_id": "thread-1",
        "title": "Investigate drift",
        "status": "active",
    }
