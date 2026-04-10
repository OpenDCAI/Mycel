from backend.web.services import monitor_service


class _FakeMonitorRepo:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows
        self.closed = False
        self.list_calls = 0

    def list_sessions_with_leases(self) -> list[dict]:
        self.list_calls += 1
        return list(self._rows)

    def close(self) -> None:
        self.closed = True


def test_runtime_health_snapshot_uses_batch_monitor_repo_for_sessions(monkeypatch):
    repo = _FakeMonitorRepo(
        [
            {"provider": "local", "lease_id": "lease-1", "thread_id": "thread-1"},
            {"provider": "local", "lease_id": "lease-2", "thread_id": "thread-2"},
            {"provider": "daytona_selfhost", "lease_id": "lease-3", "thread_id": "thread-3"},
        ]
    )
    monkeypatch.setattr(
        monitor_service,
        "runtime_health_summary",
        lambda: {"db": {"strategy": "supabase", "schema": "staging", "counts": {"chat_sessions": 3}}},
    )
    monkeypatch.setattr(monitor_service, "make_runtime_health_monitor_repo", lambda: repo)
    monkeypatch.setattr(
        monitor_service,
        "init_providers_and_managers",
        lambda: (_ for _ in ()).throw(AssertionError("health must not init providers for session counts")),
    )

    payload = monitor_service.runtime_health_snapshot()

    assert payload["db"]["strategy"] == "supabase"
    assert payload["sessions"] == {
        "total": 3,
        "providers": {
            "local": 2,
            "daytona_selfhost": 1,
        },
    }
    assert repo.list_calls == 1
    assert repo.closed is True
