from backend.web.services import resource_service


class _FakeRepo:
    def __init__(self, rows):
        self._rows = rows

    def list_sessions_with_leases(self):
        return list(self._rows)

    def close(self):
        pass


def test_list_resource_providers_deduplicates_terminal_fallback_rows(monkeypatch):
    rows = [
        {
            "provider": "local",
            "session_id": None,
            "thread_id": "thread-1",
            "lease_id": "lease-1",
            "observed_state": "running",
            "desired_state": "running",
            "created_at": "2026-04-04T00:00:00",
        },
        {
            "provider": "local",
            "session_id": None,
            "thread_id": "thread-1",
            "lease_id": "lease-1",
            "observed_state": "running",
            "desired_state": "running",
            "created_at": "2026-04-04T00:00:00",
        },
    ]

    monkeypatch.setattr(
        resource_service,
        "SQLiteSandboxMonitorRepo",
        lambda: _FakeRepo(rows),
    )
    monkeypatch.setattr(
        resource_service,
        "available_sandbox_types",
        lambda: [{"name": "local", "available": True}],
    )
    monkeypatch.setattr(
        resource_service,
        "_resolve_instance_capabilities",
        lambda _config_name: (resource_service._empty_capabilities(), None),
    )
    monkeypatch.setattr(
        resource_service,
        "_thread_owners",
        lambda thread_ids: {
            tid: {"member_id": "member-1", "member_name": "Toad", "avatar_url": None}
            for tid in thread_ids
        },
    )
    monkeypatch.setattr(resource_service, "list_snapshots_by_lease_ids", lambda _lease_ids: {})

    payload = resource_service.list_resource_providers()
    local = payload["providers"][0]

    assert local["telemetry"]["running"]["used"] == 1
    assert local["sessions"] == [
        {
            "id": "lease-1:thread-1",
            "leaseId": "lease-1",
            "threadId": "thread-1",
            "memberId": "member-1",
            "memberName": "Toad",
            "avatarUrl": None,
            "status": "running",
            "startedAt": "2026-04-04T00:00:00",
            "metrics": None,
        }
    ]
