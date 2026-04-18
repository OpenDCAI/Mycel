from pathlib import Path

from backend.web.services import sandbox_service


class _FakeLeaseStore:
    def adopt_instance(self, **kwargs):
        raise AssertionError("provider orphan mutation must not create a fake lease")

    def delete(self, lease_id: str):
        raise AssertionError(f"provider orphan mutation must not delete fake lease {lease_id}")


class _FakeProvider:
    name = "daytona_selfhost"

    def __init__(self):
        self.destroyed = []

    def destroy_session(self, session_id: str, sync: bool = True):
        self.destroyed.append((session_id, sync))
        return True


class _FakeLease:
    def __init__(self):
        self.paused = []

    def pause_instance(self, provider, *, source: str):
        self.paused.append((provider, source))
        return True


class _FakeManager:
    def __init__(self):
        self.db_path = Path("/tmp/sandbox.db")
        self.provider = _FakeProvider()
        self.lease_store = _FakeLeaseStore()
        self.lease = None

    def get_lease(self, lease_id):
        return self.lease if lease_id == "lease-1" else None


def test_mutate_sandbox_session_destroys_provider_orphan_without_fake_lease(monkeypatch):
    manager = _FakeManager()
    sessions = [
        {
            "session_id": "sandbox-1",
            "provider": "daytona_selfhost",
            "status": "running",
            "thread_id": "(orphan)",
            "lease_id": None,
        }
    ]

    monkeypatch.setattr(sandbox_service, "init_providers_and_managers", lambda: ({}, {"daytona_selfhost": manager}))
    monkeypatch.setattr(sandbox_service, "load_all_sessions", lambda _managers: sessions)

    payload = sandbox_service.mutate_sandbox_session(
        session_id="sandbox-1",
        action="destroy",
        provider_hint="daytona_selfhost",
    )

    assert payload["ok"] is True
    assert payload["mode"] == "provider_orphan_direct"
    assert payload["lease_id"] is None
    assert manager.provider.destroyed == [("sandbox-1", True)]


def test_mutate_sandbox_session_reports_manager_runtime_for_lower_runtime_handle(monkeypatch):
    manager = _FakeManager()
    manager.lease = _FakeLease()
    sessions = [
        {
            "session_id": "sandbox-1",
            "provider": "daytona_selfhost",
            "status": "running",
            "thread_id": "(orphan)",
            "lease_id": "lease-1",
        }
    ]

    monkeypatch.setattr(sandbox_service, "init_providers_and_managers", lambda: ({}, {"daytona_selfhost": manager}))
    monkeypatch.setattr(sandbox_service, "load_all_sessions", lambda _managers: sessions)

    payload = sandbox_service.mutate_sandbox_session(
        session_id="sandbox-1",
        action="pause",
        provider_hint="daytona_selfhost",
    )

    assert payload["ok"] is True
    assert payload["mode"] == "manager_runtime"
    assert payload["lease_id"] == "lease-1"
    assert manager.lease.paused == [(manager.provider, "api")]
