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


def test_get_monitor_provider_detail_fails_loudly_when_provider_missing(monkeypatch):
    monkeypatch.setattr(monitor_service, "get_resource_overview_snapshot", lambda: {"providers": []})

    with pytest.raises(KeyError, match="Provider not found: ghost"):
        monitor_service.get_monitor_provider_detail("ghost")


def test_get_monitor_lease_detail_merges_monitor_repo_truth(monkeypatch):
    class FakeRepo:
        def query_lease(self, lease_id):
            return {
                "lease_id": lease_id,
                "provider_name": "daytona",
                "desired_state": "running",
                "observed_state": "running",
                "updated_at": "2026-04-08T00:00:00Z",
                "current_instance_id": "runtime-1",
                "last_error": None,
            }

        def query_lease_threads(self, lease_id):
            return [{"thread_id": "thread-1"}]

        def query_lease_sessions(self, lease_id):
            return [{"chat_session_id": "session-1", "thread_id": "thread-1", "status": "active"}]

        def query_lease_instance_id(self, lease_id):
            return "runtime-1"

        def close(self):
            return None

    monkeypatch.setattr(monitor_service, "make_sandbox_monitor_repo", lambda: FakeRepo())

    payload = monitor_service.get_monitor_lease_detail("lease-1")

    assert payload["lease"]["lease_id"] == "lease-1"
    assert payload["provider"] == {"id": "daytona", "name": "daytona"}
    assert payload["runtime"] == {"runtime_session_id": "runtime-1"}
    assert payload["threads"] == [{"thread_id": "thread-1"}]
    assert payload["sessions"] == [{"chat_session_id": "session-1", "thread_id": "thread-1", "status": "active", "started_at": None, "ended_at": None, "close_reason": None}]


def test_get_monitor_lease_detail_exposes_cleanup_truth(monkeypatch):
    class FakeRepo:
        def query_lease(self, lease_id):
            return {
                "lease_id": lease_id,
                "provider_name": "daytona",
                "desired_state": "running",
                "observed_state": "detached",
                "updated_at": "2026-04-08T00:00:00Z",
                "current_instance_id": "runtime-1",
                "last_error": None,
            }

        def query_lease_threads(self, lease_id):
            return []

        def query_lease_sessions(self, lease_id):
            return []

        def query_lease_instance_id(self, lease_id):
            return "runtime-1"

        def close(self):
            return None

    monkeypatch.setattr(monitor_service, "make_sandbox_monitor_repo", lambda: FakeRepo())

    payload = monitor_service.get_monitor_lease_detail("lease-1")

    assert payload["cleanup"] == {
        "allowed": True,
        "recommended_action": "lease_cleanup",
        "reason": "Lease is orphan cleanup residue and can enter managed cleanup.",
        "operation": None,
        "recent_operations": [],
    }


def test_get_monitor_lease_detail_allows_detached_residue_cleanup_without_active_sessions(monkeypatch):
    class FakeRepo:
        def query_lease(self, lease_id):
            return {
                "lease_id": lease_id,
                "provider_name": "daytona",
                "desired_state": "running",
                "observed_state": "detached",
                "updated_at": "2026-04-08T00:00:00Z",
                "current_instance_id": "runtime-1",
                "last_error": None,
            }

        def query_lease_threads(self, lease_id):
            return [{"thread_id": "thread-historical"}]

        def query_lease_sessions(self, lease_id):
            return []

        def query_lease_instance_id(self, lease_id):
            return "runtime-1"

        def close(self):
            return None

    monkeypatch.setattr(monitor_service, "make_sandbox_monitor_repo", lambda: FakeRepo())

    payload = monitor_service.get_monitor_lease_detail("lease-1")

    assert payload["triage"]["category"] == "detached_residue"
    assert payload["cleanup"] == {
        "allowed": True,
        "recommended_action": "lease_cleanup",
        "reason": "Lease is detached residue and can enter managed cleanup.",
        "operation": None,
        "recent_operations": [],
    }


def test_get_monitor_lease_detail_allows_detached_residue_cleanup_without_runtime_session(monkeypatch):
    class FakeRepo:
        def query_lease(self, lease_id):
            return {
                "lease_id": lease_id,
                "provider_name": "daytona",
                "desired_state": "running",
                "observed_state": "detached",
                "updated_at": "2026-04-08T00:00:00Z",
                "current_instance_id": None,
                "last_error": None,
            }

        def query_lease_threads(self, lease_id):
            return [{"thread_id": "thread-historical"}]

        def query_lease_sessions(self, lease_id):
            return []

        def query_lease_instance_id(self, lease_id):
            return None

        def close(self):
            return None

    monkeypatch.setattr(monitor_service, "make_sandbox_monitor_repo", lambda: FakeRepo())

    payload = monitor_service.get_monitor_lease_detail("lease-1")

    assert payload["runtime"] == {"runtime_session_id": None}
    assert payload["cleanup"] == {
        "allowed": True,
        "recommended_action": "lease_cleanup",
        "reason": "Lease is detached residue and can enter managed cleanup.",
        "operation": None,
        "recent_operations": [],
    }


def test_get_monitor_lease_detail_ignores_stale_thread_refs_when_classifying_triage(monkeypatch):
    class FakeRepo:
        def query_lease(self, lease_id):
            return {
                "lease_id": lease_id,
                "provider_name": "daytona",
                "desired_state": "paused",
                "observed_state": "paused",
                "updated_at": "2026-04-08T00:00:00Z",
                "current_instance_id": "runtime-1",
                "last_error": None,
            }

        def query_lease_threads(self, lease_id):
            return [{"thread_id": "thread-gone"}]

        def query_lease_sessions(self, lease_id):
            return []

        def query_lease_instance_id(self, lease_id):
            return "runtime-1"

        def close(self):
            return None

    monkeypatch.setattr(monitor_service, "make_sandbox_monitor_repo", lambda: FakeRepo())
    monkeypatch.setattr(monitor_service, "_live_thread_ids", lambda thread_ids: set())

    payload = monitor_service.get_monitor_lease_detail("lease-1")

    assert payload["threads"] == []
    assert payload["triage"]["category"] == "orphan_cleanup"
    assert payload["cleanup"] == {
        "allowed": True,
        "recommended_action": "lease_cleanup",
        "reason": "Lease is orphan cleanup residue and can enter managed cleanup.",
        "operation": None,
        "recent_operations": [],
    }


def test_request_monitor_lease_cleanup_uses_lease_destroy_for_detached_residue(monkeypatch):
    calls: list[tuple[str, str]] = []

    class FakeRepo:
        def query_lease(self, lease_id):
            return {
                "lease_id": lease_id,
                "provider_name": "daytona",
                "desired_state": "running",
                "observed_state": "detached",
                "updated_at": "2026-04-08T00:00:00Z",
                "current_instance_id": None,
                "last_error": None,
            }

        def query_lease_threads(self, lease_id):
            return [{"thread_id": "thread-historical"}]

        def query_lease_sessions(self, lease_id):
            return []

        def query_lease_instance_id(self, lease_id):
            return "runtime-1"

        def close(self):
            return None

    def _destroy_sandbox_lease(*, lease_id: str, provider_name: str):
        calls.append((lease_id, provider_name))
        return {
            "ok": True,
            "action": "destroy",
            "lease_id": lease_id,
            "provider": provider_name,
            "mode": "manager_lease",
        }

    monkeypatch.setattr(monitor_service, "make_sandbox_monitor_repo", lambda: FakeRepo())
    monkeypatch.setattr(
        "backend.web.services.sandbox_service.destroy_sandbox_lease",
        _destroy_sandbox_lease,
        raising=False,
    )

    payload = monitor_service.request_monitor_lease_cleanup("lease-1")

    assert payload["accepted"] is True
    assert payload["message"] == "Lease cleanup completed."
    assert payload["operation"]["kind"] == "lease_cleanup"
    assert calls == [("lease-1", "daytona")]


def test_request_monitor_lease_cleanup_allows_detached_residue_without_runtime_session(monkeypatch):
    calls: list[tuple[str, str]] = []

    class FakeRepo:
        def query_lease(self, lease_id):
            return {
                "lease_id": lease_id,
                "provider_name": "daytona",
                "desired_state": "running",
                "observed_state": "detached",
                "updated_at": "2026-04-08T00:00:00Z",
                "current_instance_id": None,
                "last_error": None,
            }

        def query_lease_threads(self, lease_id):
            return [{"thread_id": "thread-historical"}]

        def query_lease_sessions(self, lease_id):
            return []

        def query_lease_instance_id(self, lease_id):
            return None

        def close(self):
            return None

    def _destroy_sandbox_lease(*, lease_id: str, provider_name: str):
        calls.append((lease_id, provider_name))
        return {
            "ok": True,
            "action": "destroy",
            "lease_id": lease_id,
            "provider": provider_name,
            "mode": "manager_lease",
        }

    monkeypatch.setattr(monitor_service, "make_sandbox_monitor_repo", lambda: FakeRepo())
    monkeypatch.setattr(
        "backend.web.services.sandbox_service.destroy_sandbox_lease",
        _destroy_sandbox_lease,
        raising=False,
    )

    payload = monitor_service.request_monitor_lease_cleanup("lease-1")

    assert payload["accepted"] is True
    assert payload["message"] == "Lease cleanup completed."
    assert payload["operation"]["kind"] == "lease_cleanup"
    assert calls == [("lease-1", "daytona")]


def test_get_monitor_lease_detail_fails_loudly_when_lease_missing(monkeypatch):
    class FakeRepo:
        def query_lease(self, lease_id):
            return None

        def close(self):
            return None

    monkeypatch.setattr(monitor_service, "make_sandbox_monitor_repo", lambda: FakeRepo())

    with pytest.raises(KeyError, match="Lease not found: lease-404"):
        monitor_service.get_monitor_lease_detail("lease-404")


def test_list_leases_ignores_stale_thread_refs_when_classifying_triage(monkeypatch):
    class FakeRepo:
        def query_leases(self):
            return [
                {
                    "lease_id": "lease-1",
                    "provider_name": "daytona",
                    "desired_state": "paused",
                    "observed_state": "paused",
                    "current_instance_id": "runtime-1",
                    "last_error": None,
                    "updated_at": "2026-04-08T00:00:00Z",
                    "thread_id": "thread-gone",
                }
            ]

        def close(self):
            return None

    monkeypatch.setattr(monitor_service, "make_sandbox_monitor_repo", lambda: FakeRepo())
    monkeypatch.setattr(monitor_service, "_live_thread_ids", lambda thread_ids: set())

    payload = monitor_service.list_leases()

    assert payload["triage"]["summary"]["orphan_cleanup"] == 1
    assert payload["triage"]["summary"]["healthy_capacity"] == 0
    assert payload["items"][0]["thread"] == {"thread_id": None, "is_orphan": True}
    assert payload["items"][0]["triage"]["category"] == "orphan_cleanup"


@pytest.mark.asyncio
async def test_get_monitor_thread_detail_exposes_trajectory_truth(monkeypatch):
    class FakeThreadRepo:
        def get_by_id(self, thread_id):
            return {
                "id": thread_id,
                "thread_id": thread_id,
                "title": "Investigate sandbox drift",
                "status": "active",
            }

    class FakeMonitorRepo:
        def query_thread_summary(self, thread_id):
            return {
                "provider_name": "daytona",
                "lease_id": "lease-1",
                "current_instance_id": "runtime-1",
                "desired_state": "running",
                "observed_state": "running",
            }

        def query_thread_sessions(self, thread_id):
            return [{"chat_session_id": "session-1", "status": "active"}]

        def close(self):
            return None

    class FakeBatchService:
        def list_batch_runs_for_thread(self, thread_id):
            return [
                {
                    "batch_run_id": "batch-run-1",
                    "batch_id": "batch-1",
                    "scenario_id": "scenario-1",
                    "thread_id": thread_id,
                    "eval_run_id": "eval-run-1",
                }
            ]

    monkeypatch.setattr(monitor_service, "make_sandbox_monitor_repo", lambda: FakeMonitorRepo())
    monkeypatch.setattr(monitor_service, "make_eval_batch_service", lambda: FakeBatchService())
    monkeypatch.setattr(
        monitor_service,
        "_thread_owners",
        lambda *_args, **_kwargs: {
            "thread-1": {
                "user_id": "user-1",
                "display_name": "Ada",
                "email": "ada@example.com",
            }
        },
    )
    monkeypatch.setattr(
        "backend.web.services.monitor_trace_service.build_monitor_thread_trajectory",
        AsyncMock(
            return_value={
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
            }
        ),
    )

    app = SimpleNamespace(state=SimpleNamespace(thread_repo=FakeThreadRepo(), user_repo=object()))

    payload = await monitor_service.get_monitor_thread_detail(app, "thread-1")

    assert payload["thread"]["thread_id"] == "thread-1"
    assert payload["owner"]["display_name"] == "Ada"
    assert payload["trajectory"]["run_id"] == "run-1"
    assert payload["trajectory"]["conversation"][0]["role"] == "human"
    assert payload["trajectory"]["events"][0]["event_type"] == "tool_call"
    assert payload["evaluation_batch_runs"] == [
        {
            "batch_run_id": "batch-run-1",
            "batch_id": "batch-1",
            "scenario_id": "scenario-1",
            "thread_id": "thread-1",
            "eval_run_id": "eval-run-1",
        }
    ]


def test_monitor_detail_contracts_do_not_create_resource_cache_import_cycle():
    result = subprocess.run(
        [sys.executable, "-c", "import backend.web.main"],
        capture_output=True,
        text=True,
        cwd=".",
    )

    assert result.returncode == 0, result.stderr


@pytest.mark.asyncio
async def test_get_monitor_thread_detail_derives_summary_from_session_truth_when_repo_summary_missing(monkeypatch):
    class FakeThreadRepo:
        def get_by_id(self, thread_id):
            return {"id": thread_id, "status": "active"}

    class FakeMonitorRepo:
        def query_thread_summary(self, thread_id):
            return None

        def query_thread_sessions(self, thread_id):
            return [
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

        def close(self):
            return None

    monkeypatch.setattr(monitor_service, "make_sandbox_monitor_repo", lambda: FakeMonitorRepo())
    monkeypatch.setattr(
        monitor_service,
        "_thread_owners",
        lambda _thread_ids, **_kwargs: {"thread-1": {"agent_user_id": "agent-1", "agent_name": "Toad"}},
    )
    monkeypatch.setattr(
        "backend.web.services.monitor_trace_service.build_monitor_thread_trajectory",
        AsyncMock(return_value={"run_id": None, "conversation": [], "events": []}),
    )

    app = SimpleNamespace(state=SimpleNamespace(thread_repo=FakeThreadRepo(), user_repo=None))

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
    class FakeThreadRepo:
        def get_by_id(self, thread_id):
            return {"id": thread_id, "status": "active"}

    class FakeMonitorRepo:
        def query_thread_summary(self, thread_id):
            return None

        def query_thread_sessions(self, thread_id):
            return []

        def close(self):
            return None

    monkeypatch.setattr(monitor_service, "make_sandbox_monitor_repo", lambda: FakeMonitorRepo())
    monkeypatch.setattr(
        monitor_service,
        "_thread_owners",
        lambda _thread_ids, **_kwargs: {
            "thread-1": {"agent_user_id": "agent-1", "agent_name": "Toad", "avatar_url": "/api/users/agent-1/avatar"}
        },
    )
    monkeypatch.setattr(
        "backend.web.services.monitor_trace_service.build_monitor_thread_trajectory",
        AsyncMock(return_value={"run_id": None, "conversation": [], "events": []}),
    )

    app = SimpleNamespace(state=SimpleNamespace(thread_repo=FakeThreadRepo(), user_repo=None))

    payload = await monitor_service.get_monitor_thread_detail(app, "thread-1")

    assert payload["owner"] == {
        "user_id": "agent-1",
        "display_name": "Toad",
        "email": None,
        "avatar_url": "/api/users/agent-1/avatar",
    }


@pytest.mark.asyncio
async def test_get_monitor_thread_detail_normalizes_thread_shape_for_frontend(monkeypatch):
    class FakeThreadRepo:
        def get_by_id(self, thread_id):
            return {"id": thread_id, "title": "Investigate drift", "status": "active"}

    class FakeMonitorRepo:
        def query_thread_summary(self, thread_id):
            return None

        def query_thread_sessions(self, thread_id):
            return []

        def close(self):
            return None

    monkeypatch.setattr(monitor_service, "make_sandbox_monitor_repo", lambda: FakeMonitorRepo())
    monkeypatch.setattr(monitor_service, "_thread_owners", lambda *_args, **_kwargs: {"thread-1": None})
    monkeypatch.setattr(
        "backend.web.services.monitor_trace_service.build_monitor_thread_trajectory",
        AsyncMock(return_value={"run_id": None, "conversation": [], "events": []}),
    )

    app = SimpleNamespace(state=SimpleNamespace(thread_repo=FakeThreadRepo(), user_repo=None))

    payload = await monitor_service.get_monitor_thread_detail(app, "thread-1")

    assert payload["thread"] == {
        "id": "thread-1",
        "thread_id": "thread-1",
        "title": "Investigate drift",
        "status": "active",
    }
