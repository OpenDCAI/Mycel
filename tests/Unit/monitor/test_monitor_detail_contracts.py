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
