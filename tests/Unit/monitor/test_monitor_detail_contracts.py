import inspect
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


@pytest.fixture(autouse=True)
def _default_monitor_thread_repo(monkeypatch):
    class FakeCanonicalThreadRepo:
        def list_by_ids(self, thread_ids: list[str]):
            return [{"id": thread_id, "agent_user_id": "agent-1", "branch_index": 0, "is_main": True} for thread_id in thread_ids]

        def close(self):
            return None

    monkeypatch.setattr(monitor_service, "build_thread_repo", lambda: FakeCanonicalThreadRepo())


@pytest.fixture(autouse=True)
def _clear_monitor_cleanup_operations():
    monitor_service.monitor_operation_service._OPERATIONS.clear()
    monitor_service.monitor_operation_service._TARGET_INDEX.clear()


def _sandbox_row(**overrides):
    row = {
        "sandbox_id": "sandbox-1",
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


class FakeSandboxMonitorRepo:
    def __init__(self, *, sandbox=None, threads=None, sessions=None, runtime_session_id="runtime-1", sandboxes=None):
        self.sandbox = sandbox
        self.threads = threads or []
        self.sessions = sessions or []
        self.runtime_session_id = runtime_session_id
        self.sandboxes = sandboxes or []

    def query_sandbox(self, sandbox_id):
        sandbox = self.sandbox if self.sandbox is not None else _sandbox_row(sandbox_id=sandbox_id)
        if sandbox is _MISSING:
            return None
        result = {**sandbox, "sandbox_id": sandbox.get("sandbox_id") or sandbox_id}
        result.pop("lease_id", None)
        return result

    def query_sandbox_cleanup_target(self, sandbox_id):
        sandbox = self.sandbox if self.sandbox is not None else _sandbox_row(sandbox_id=sandbox_id)
        if sandbox is _MISSING:
            return None
        return {
            "sandbox_id": sandbox.get("sandbox_id") or sandbox_id,
            "provider_name": sandbox.get("provider_name"),
            "provider_env_id": sandbox.get("current_instance_id"),
            "lower_runtime_handle": str(sandbox.get("lease_id") or "").strip() or None,
        }

    def query_sandboxes(self):
        if self.sandboxes:
            return self.sandboxes
        if self.sandbox is _MISSING:
            return []
        if self.sandbox is not None:
            return [self.sandbox]
        return [_sandbox_row()]

    def query_sandbox_threads(self, _sandbox_id):
        return self.threads

    def query_sandbox_sessions(self, _sandbox_id):
        return self.sessions

    def query_sandbox_instance_id(self, _sandbox_id):
        return self.runtime_session_id

    def close(self):
        return None


def _use_monitor_repo(monkeypatch, repo):
    monkeypatch.setattr(monitor_service, "make_sandbox_monitor_repo", lambda: repo)


def _detached_sandbox(**overrides):
    return _sandbox_row(desired_state="running", observed_state="detached", **overrides)


def _cleanup_state(reason: str):
    return {
        "allowed": True,
        "recommended_action": "sandbox_cleanup",
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
    def _destroy_sandbox_runtime(*, lower_runtime_handle: str, provider_name: str, detach_thread_bindings: bool = False):
        calls.append((lower_runtime_handle, provider_name, detach_thread_bindings))
        return {
            "ok": True,
            "action": "destroy",
            "lower_runtime_handle": lower_runtime_handle,
            "provider": provider_name,
            "mode": "manager_runtime",
        }

    return _destroy_sandbox_runtime


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
                        {
                            "leaseId": "lease-1",
                            "sandboxId": "sandbox-1",
                            "threadId": "thread-1",
                            "runtimeSessionId": "runtime-1",
                        },
                        {"leaseId": "lease-2", "sandboxId": "sandbox-2", "threadId": "thread-2"},
                    ],
                }
            ]
        },
    )

    payload = monitor_service.get_monitor_provider_detail("daytona")

    assert payload["provider"]["id"] == "daytona"
    assert payload["sandbox_ids"] == ["sandbox-1", "sandbox-2"]
    assert "lease_ids" not in payload
    assert "thread_ids" not in payload
    assert payload["runtime_session_ids"] == ["runtime-1"]

    assert monitor_service._resource_row_values(
        [
            {"sandboxId": "sandbox-2"},
            {"sandboxId": ""},
            {"sandboxId": "sandbox-1"},
            {"sandboxId": "sandbox-1"},
        ],
        "sandboxId",
    ) == ["sandbox-1", "sandbox-2"]


def test_get_monitor_runtime_detail_exposes_sandbox_identity(monkeypatch):
    monkeypatch.setattr(
        monitor_service,
        "get_resource_overview_snapshot",
        lambda: {
            "providers": [
                {
                    "id": "daytona",
                    "name": "daytona",
                    "status": "active",
                    "sessions": [
                        {
                            "runtimeSessionId": "runtime-1",
                            "leaseId": "lease-1",
                            "sandboxId": "sandbox-1",
                            "threadId": "thread-1",
                        }
                    ],
                }
            ]
        },
    )

    payload = monitor_service.get_monitor_runtime_detail("runtime-1")

    assert payload["sandbox_id"] == "sandbox-1"
    assert "lease_id" not in payload
    assert payload["thread_id"] == "thread-1"


def test_get_monitor_runtime_detail_uses_resource_row_local_naming():
    source = inspect.getsource(monitor_service.get_monitor_runtime_detail)
    old_loop_token = "for " + "session in provider.get"
    old_runtime_payload_token = '"runtime": ' + "session"

    assert old_loop_token not in source
    assert old_runtime_payload_token not in source


def test_get_monitor_sandbox_configs_reads_runtime_inventory(monkeypatch, tmp_path):
    monkeypatch.setattr(monitor_service.web_config, "LOCAL_WORKSPACE_ROOT", tmp_path)
    monkeypatch.setattr(
        monitor_service.sandbox_service,
        "available_sandbox_types",
        lambda: [
            {"name": "local", "provider": "local", "available": True},
            {"name": "daytona_selfhost", "provider": "daytona", "available": False, "reason": "missing key"},
        ],
    )

    payload = monitor_service.get_monitor_sandbox_configs()

    assert payload == {
        "source": "runtime_sandbox_inventory",
        "default_local_cwd": str(tmp_path),
        "count": 2,
        "providers": [
            {"name": "local", "provider": "local", "available": True},
            {"name": "daytona_selfhost", "provider": "daytona", "available": False, "reason": "missing key"},
        ],
    }


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


def test_get_monitor_sandbox_detail_merges_monitor_repo_state(monkeypatch):
    _use_monitor_repo(
        monkeypatch,
        FakeSandboxMonitorRepo(
            threads=[{"thread_id": "thread-1"}],
            sessions=[{"chat_session_id": "session-1", "thread_id": "thread-1", "status": "active"}],
        ),
    )

    payload = monitor_service.get_monitor_sandbox_detail("sandbox-1")

    assert payload["sandbox"]["sandbox_id"] == "sandbox-1"
    assert payload["provider"] == {"id": "daytona", "name": "daytona"}
    assert payload["runtime"] == {"runtime_session_id": "runtime-1"}
    assert payload["threads"] == [{"thread_id": "thread-1"}]
    assert payload["cleanup"]["allowed"] is False
    assert "lease" not in payload


def test_get_monitor_sandbox_detail_collapses_live_threads_to_canonical_primary_thread(monkeypatch):
    _use_monitor_repo(
        monkeypatch,
        FakeSandboxMonitorRepo(
            threads=[{"thread_id": "thread-child"}, {"thread_id": "thread-main"}],
            sessions=[{"chat_session_id": "session-1", "thread_id": "thread-main", "status": "active"}],
        ),
    )

    class _ThreadRepo:
        def list_by_ids(self, thread_ids: list[str]):
            assert thread_ids == ["thread-child", "thread-main"]
            return [
                {"id": "thread-child", "agent_user_id": "agent-1", "branch_index": 2, "is_main": False},
                {"id": "thread-main", "agent_user_id": "agent-1", "branch_index": 0, "is_main": True},
            ]

        def close(self):
            return None

    monkeypatch.setattr(monitor_service, "build_thread_repo", lambda: _ThreadRepo())

    payload = monitor_service.get_monitor_sandbox_detail("sandbox-1")

    assert payload["threads"] == [{"thread_id": "thread-main"}]


def test_list_monitor_sandboxes_is_canonical_single_emit(monkeypatch):
    _use_monitor_repo(
        monkeypatch,
        FakeSandboxMonitorRepo(
            sandboxes=[
                _sandbox_row(
                    sandbox_id="sandbox-1",
                    lease_id="lease-1",
                    desired_state="paused",
                    observed_state="paused",
                    thread_id="thread-gone",
                )
            ]
        ),
    )
    monkeypatch.setattr(monitor_service, "_live_thread_ids", lambda thread_ids: set())

    payload = monitor_service.list_monitor_sandboxes()

    assert payload["source"] == "sandbox_canonical"
    assert payload["items"][0]["sandbox_id"] == "sandbox-1"
    assert "lease_id" not in payload["items"][0]


def test_get_monitor_sandbox_detail_is_canonical_single_emit(monkeypatch):
    _use_monitor_repo(
        monkeypatch,
        FakeSandboxMonitorRepo(
            sandbox=_sandbox_row(),
            threads=[{"thread_id": "thread-1"}],
            sessions=[{"chat_session_id": "session-1", "thread_id": "thread-1", "status": "active"}],
        ),
    )

    payload = monitor_service.get_monitor_sandbox_detail("sandbox-1")

    assert payload["source"] == "sandbox_canonical"
    assert payload["sandbox"]["sandbox_id"] == "sandbox-1"
    assert "lease_id" not in payload["sandbox"]
    assert payload["cleanup"]["allowed"] is False
    assert payload["cleanup"]["recommended_action"] is None


def test_get_monitor_sandbox_detail_exposes_cleanup_state(monkeypatch):
    _use_monitor_repo(monkeypatch, FakeSandboxMonitorRepo(sandbox=_detached_sandbox()))

    payload = monitor_service.get_monitor_sandbox_detail("sandbox-1")

    assert payload["sandbox"]["sandbox_id"] == "sandbox-1"
    assert payload["cleanup"] == _cleanup_state("Sandbox is orphan cleanup residue and can enter managed cleanup.")


def test_get_monitor_sandbox_detail_allows_missing_lower_runtime_handle_for_readonly_detail(monkeypatch):
    _use_monitor_repo(
        monkeypatch,
        FakeSandboxMonitorRepo(
            sandbox=_sandbox_row(lease_id=None, provider_name="local", observed_state="running", desired_state="running"),
            threads=[],
            sessions=[],
            runtime_session_id="runtime-1",
        ),
    )

    payload = monitor_service.get_monitor_sandbox_detail("sandbox-1")

    assert payload["sandbox"]["sandbox_id"] == "sandbox-1"
    assert payload["runtime"]["runtime_session_id"] == "runtime-1"
    assert payload["cleanup"] == {
        "allowed": False,
        "recommended_action": None,
        "reason": "Sandbox cleanup requires a managed runtime handle.",
        "operation": None,
        "recent_operations": [],
    }


def test_request_monitor_sandbox_cleanup_uses_canonical_sandbox_target(monkeypatch):
    calls: list[tuple[str, str, bool]] = []
    _use_monitor_repo(
        monkeypatch,
        FakeSandboxMonitorRepo(
            sandbox=_detached_sandbox(),
            threads=[{"thread_id": "thread-historical"}],
            runtime_session_id="runtime-1",
        ),
    )
    monkeypatch.setattr(
        "backend.web.services.sandbox_service.destroy_sandbox_runtime",
        _record_destroy(calls),
        raising=False,
    )

    payload = monitor_service.request_monitor_sandbox_cleanup("sandbox-1")

    assert payload["accepted"] is True
    assert payload["message"] == "Sandbox cleanup completed."
    assert payload["current_truth"] == {
        "sandbox_id": "sandbox-1",
        "triage_category": "detached_residue",
    }
    assert "lease_id" not in payload["current_truth"]
    assert payload["operation"]["kind"] == "sandbox_cleanup"
    assert payload["operation"]["target_type"] == "sandbox"
    assert payload["operation"]["target_id"] == "sandbox-1"
    assert payload["operation"]["result_truth"]["sandbox_state_before"] == "detached"
    assert payload["operation"]["result_truth"]["sandbox_state_after"] is None
    assert "lease_state_before" not in payload["operation"]["result_truth"]
    assert "lease_state_after" not in payload["operation"]["result_truth"]
    assert calls == [("lease-1", "daytona", True)]


def test_request_monitor_sandbox_cleanup_keeps_lower_handle_out_of_sandbox_payload(monkeypatch):
    captured: dict[str, object] = {}
    _use_monitor_repo(monkeypatch, FakeSandboxMonitorRepo(sandbox=_detached_sandbox(), runtime_session_id="runtime-1"))

    def _record_request(payload):
        captured.update(payload)
        return {"accepted": True}

    monkeypatch.setattr(monitor_service.monitor_operation_service, "request_sandbox_cleanup", _record_request)

    assert monitor_service.request_monitor_sandbox_cleanup("sandbox-1") == {"accepted": True}

    assert "lease" not in captured
    assert "lease_id" not in captured["sandbox"]
    assert captured["lower_runtime"] == {"handle": "lease-1"}


def test_sandbox_cleanup_operation_rejects_missing_lower_runtime_handle(monkeypatch):
    calls: list[tuple[str, str, bool]] = []
    monkeypatch.setattr(
        "backend.web.services.sandbox_service.destroy_sandbox_runtime",
        _record_destroy(calls),
        raising=False,
    )

    payload = monitor_service.monitor_operation_service.request_sandbox_cleanup(
        {
            "sandbox": _detached_sandbox(),
            "lower_runtime": {"handle": ""},
            "triage": {"category": "orphan_cleanup"},
            "provider": {"id": "daytona"},
            "runtime": {"runtime_session_id": "runtime-1"},
            "threads": [],
            "sessions": [],
            "cleanup": _cleanup_state("Sandbox is orphan cleanup residue and can enter managed cleanup."),
        }
    )

    assert payload == {
        "accepted": False,
        "message": "Sandbox cleanup requires a managed runtime handle.",
        "operation": None,
        "current_truth": {
            "sandbox_id": "sandbox-1",
            "triage_category": "orphan_cleanup",
        },
    }
    assert calls == []


def test_get_monitor_sandbox_detail_shows_recent_sandbox_cleanup_operation(monkeypatch):
    calls: list[tuple[str, str, bool]] = []
    repo = FakeSandboxMonitorRepo(
        sandbox=_detached_sandbox(),
        threads=[{"thread_id": "thread-historical"}],
        runtime_session_id="runtime-1",
    )
    _use_monitor_repo(monkeypatch, repo)
    monkeypatch.setattr(
        "backend.web.services.sandbox_service.destroy_sandbox_runtime",
        _record_destroy(calls),
        raising=False,
    )

    created = monitor_service.request_monitor_sandbox_cleanup("sandbox-1")
    detail = monitor_service.get_monitor_sandbox_detail("sandbox-1")

    assert detail["cleanup"]["operation"]["operation_id"] == created["operation"]["operation_id"]
    assert detail["cleanup"]["operation"]["target_type"] == "sandbox"
    assert detail["cleanup"]["recent_operations"][0]["target_type"] == "sandbox"
    assert calls == [("lease-1", "daytona", True)]


def test_request_monitor_provider_orphan_runtime_cleanup_uses_sandbox_manager(monkeypatch):
    calls: list[tuple[str, str, str, str | None]] = []
    monkeypatch.setattr(
        monitor_service,
        "list_monitor_provider_orphan_runtimes",
        lambda: {
            "count": 1,
            "runtimes": [
                {
                    "runtime_id": "sandbox-1",
                    "provider": "daytona_selfhost",
                    "status": "paused",
                    "source": "provider_orphan",
                }
            ],
        },
    )

    def _mutate_sandbox_session(*, session_id: str, action: str, provider_hint: str | None = None):
        calls.append((session_id, action, provider_hint or "", provider_hint))
        return {
            "ok": True,
            "action": action,
            "session_id": session_id,
            "provider": provider_hint,
            "lease_id": "lease-adopt-1",
            "mode": "manager_runtime",
        }

    monkeypatch.setattr(
        "backend.web.services.sandbox_service.mutate_sandbox_session",
        _mutate_sandbox_session,
        raising=False,
    )

    payload = monitor_service.request_monitor_provider_orphan_runtime_cleanup("daytona_selfhost", "sandbox-1")

    assert payload["accepted"] is True
    assert payload["message"] == "Provider orphan runtime cleanup completed."
    assert payload["operation"]["kind"] == "provider_orphan_runtime_cleanup"
    assert payload["operation"]["status"] == "succeeded"
    assert payload["operation"]["target_type"] == "provider_orphan_runtime"
    detail = monitor_service.get_monitor_operation_detail(payload["operation"]["operation_id"])
    destroy_result = detail["result_truth"]["destroy_result"]
    assert detail["target"] == {
        "target_type": "provider_orphan_runtime",
        "provider_id": "daytona_selfhost",
        "runtime_id": "sandbox-1",
    }
    assert destroy_result == {
        "ok": True,
        "action": "destroy",
        "session_id": "sandbox-1",
        "provider": "daytona_selfhost",
        "mode": "manager_runtime",
    }
    assert "lease_id" not in destroy_result
    assert payload["current_truth"] == {
        "provider_id": "daytona_selfhost",
        "runtime_id": "sandbox-1",
    }
    assert calls == [("sandbox-1", "destroy", "daytona_selfhost", "daytona_selfhost")]


def test_request_monitor_provider_orphan_runtime_cleanup_rejects_running_orphan(monkeypatch):
    calls: list[tuple[str, str, str | None]] = []
    monkeypatch.setattr(
        monitor_service,
        "list_monitor_provider_orphan_runtimes",
        lambda: {
            "count": 1,
            "runtimes": [
                {
                    "runtime_id": "sandbox-1",
                    "provider": "daytona_selfhost",
                    "status": "running",
                    "source": "provider_orphan",
                }
            ],
        },
    )

    def _mutate_sandbox_session(*, session_id: str, action: str, provider_hint: str | None = None):
        calls.append((session_id, action, provider_hint))
        return {"ok": True}

    monkeypatch.setattr(
        "backend.web.services.sandbox_service.mutate_sandbox_session",
        _mutate_sandbox_session,
        raising=False,
    )

    payload = monitor_service.request_monitor_provider_orphan_runtime_cleanup("daytona_selfhost", "sandbox-1")

    assert payload["accepted"] is False
    assert payload["operation"] is None
    assert "paused" in payload["message"]
    assert payload["current_truth"]["runtime_id"] == "sandbox-1"
    assert "session_id" not in payload["current_truth"]
    assert calls == []


def test_list_monitor_provider_orphan_runtimes_returns_provider_orphans(monkeypatch):
    monkeypatch.setattr(monitor_service.sandbox_service, "init_providers_and_managers", lambda: ({}, {"daytona": object()}))
    monkeypatch.setattr(
        monitor_service.sandbox_service,
        "load_provider_orphan_runtimes",
        lambda _managers: [
            {"session_id": "orphan-1", "provider": "daytona", "source": "provider_orphan", "status": "running"},
        ],
    )

    payload = monitor_service.list_monitor_provider_orphan_runtimes()

    assert payload == {
        "count": 1,
        "runtimes": [
            {
                "runtime_id": "orphan-1",
                "provider": "daytona",
                "status": "running",
                "source": "provider_orphan",
            }
        ],
    }


def test_list_monitor_sandboxes_ignores_stale_thread_refs_when_classifying_triage(monkeypatch):
    _use_monitor_repo(
        monkeypatch,
        FakeSandboxMonitorRepo(
            sandboxes=[_sandbox_row(sandbox_id="sandbox-1", desired_state="paused", observed_state="paused", thread_id="thread-gone")]
        ),
    )
    monkeypatch.setattr(monitor_service, "_live_thread_ids", lambda thread_ids: set())

    payload = monitor_service.list_monitor_sandboxes()

    assert payload["title"] == "All Sandboxes"
    assert payload["triage"]["summary"]["orphan_cleanup"] == 1
    assert payload["items"][0]["sandbox_id"] == "sandbox-1"
    assert "lease_id" not in payload["items"][0]


@pytest.mark.asyncio
async def test_get_monitor_thread_detail_exposes_trajectory_state(monkeypatch):
    _use_monitor_repo(
        monkeypatch,
        FakeMonitorThreadRepo(
            summary={
                "sandbox_id": "sandbox-1",
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
    assert payload["summary"]["sandbox_id"] == "sandbox-1"
    assert "lease_id" not in payload["summary"]
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
                    "sandbox_id": "sandbox-1",
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
        "sandbox_id": "sandbox-1",
        "provider_name": "daytona",
        "current_instance_id": "runtime-1",
        "desired_state": "paused",
        "observed_state": "paused",
    }


def test_request_monitor_sandbox_cleanup_records_sandbox_target_without_thread_list(monkeypatch):
    calls: list[tuple[str, str, bool]] = []
    _use_monitor_repo(
        monkeypatch,
        FakeSandboxMonitorRepo(
            sandbox=_detached_sandbox(),
            threads=[{"thread_id": "thread-historical"}],
            runtime_session_id="runtime-1",
        ),
    )
    monkeypatch.setattr(
        "backend.web.services.sandbox_service.destroy_sandbox_runtime",
        _record_destroy(calls),
        raising=False,
    )

    payload = monitor_service.request_monitor_sandbox_cleanup("sandbox-1")

    assert payload["accepted"] is True
    assert "thread_ids" not in (payload["operation"].get("target") or {})
    assert "thread_state_after" not in (payload["operation"].get("result_truth") or {})
    assert calls == [("lease-1", "daytona", True)]


def test_get_monitor_operation_detail_preserves_canonical_sandbox_target(monkeypatch):
    monkeypatch.setattr(
        monitor_service.monitor_operation_service,
        "get_operation_detail",
        lambda _operation_id: {
            "operation": {"operation_id": "op-1", "kind": "sandbox_cleanup", "status": "succeeded"},
            "target": {
                "target_type": "sandbox",
                "target_id": "sandbox-1",
                "provider_id": "daytona",
                "runtime_session_id": "runtime-1",
            },
            "result_truth": {
                "lease_state_before": "running",
                "lease_state_after": "destroyed",
            },
            "events": [],
        },
    )

    payload = monitor_service.get_monitor_operation_detail("op-1")

    assert payload["sandbox_id"] == "sandbox-1"
    assert payload["target"]["target_type"] == "sandbox"
    assert payload["target"]["target_id"] == "sandbox-1"


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
