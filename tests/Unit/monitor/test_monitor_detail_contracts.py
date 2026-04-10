import subprocess
import sys
from types import SimpleNamespace

import pytest

from backend.web.services import monitor_service


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


def test_get_monitor_lease_detail_fails_loudly_when_lease_missing(monkeypatch):
    class FakeRepo:
        def query_lease(self, lease_id):
            return None

        def close(self):
            return None

    monkeypatch.setattr(monitor_service, "make_sandbox_monitor_repo", lambda: FakeRepo())

    with pytest.raises(KeyError, match="Lease not found: lease-404"):
        monitor_service.get_monitor_lease_detail("lease-404")


def test_monitor_detail_contracts_do_not_create_resource_cache_import_cycle():
    result = subprocess.run(
        [sys.executable, "-c", "import backend.web.main"],
        capture_output=True,
        text=True,
        cwd=".",
    )

    assert result.returncode == 0, result.stderr


def test_get_monitor_thread_detail_derives_summary_from_session_truth_when_repo_summary_missing(monkeypatch):
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

    app = SimpleNamespace(state=SimpleNamespace(thread_repo=FakeThreadRepo(), user_repo=None))

    payload = monitor_service.get_monitor_thread_detail(app, "thread-1")

    assert payload["summary"] == {
        "provider_name": "daytona",
        "lease_id": "lease-1",
        "current_instance_id": "runtime-1",
        "desired_state": "paused",
        "observed_state": "paused",
    }
