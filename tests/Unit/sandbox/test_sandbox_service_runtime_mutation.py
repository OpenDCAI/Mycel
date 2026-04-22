from pathlib import Path

from backend.sandboxes import service as sandbox_service

LOWER_RUNTIME_KEY = "sandbox_runtime_" + "id"


class _FakeLeaseStore:
    def adopt_instance(self, **kwargs):
        raise AssertionError("provider orphan mutation must not create a fake lease")

    def delete(self, lower_runtime_id: str):
        raise AssertionError(f"provider orphan mutation must not delete fake lease {lower_runtime_id}")


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
        self.sandbox_runtime = None

    def get_sandbox_runtime(self, lower_runtime_id):
        return self.sandbox_runtime if lower_runtime_id == "lease-1" else None


def test_mutate_sandbox_runtime_destroys_provider_orphan_without_fake_lease(monkeypatch):
    manager = _FakeManager()
    runtimes = [
        {
            "session_id": "sandbox-1",
            "provider": "daytona_selfhost",
            "status": "running",
            "thread_id": "(orphan)",
            LOWER_RUNTIME_KEY: None,
        }
    ]

    monkeypatch.setattr(sandbox_service, "init_providers_and_managers", lambda: ({}, {"daytona_selfhost": manager}))
    monkeypatch.setattr(sandbox_service, "load_all_sandbox_runtimes", lambda _managers: runtimes)

    payload = sandbox_service.mutate_sandbox_runtime(
        runtime_id="sandbox-1",
        action="destroy",
        provider_hint="daytona_selfhost",
    )

    assert payload["ok"] is True
    assert payload["mode"] == "provider_orphan_direct"
    assert payload[LOWER_RUNTIME_KEY] is None
    assert manager.provider.destroyed == [("sandbox-1", True)]


def test_mutate_sandbox_runtime_reports_manager_runtime_for_sandbox_runtime_handle(monkeypatch):
    manager = _FakeManager()
    manager.sandbox_runtime = _FakeLease()
    runtimes = [
        {
            "session_id": "sandbox-1",
            "provider": "daytona_selfhost",
            "status": "running",
            "thread_id": "(orphan)",
            LOWER_RUNTIME_KEY: "lease-1",
        }
    ]

    monkeypatch.setattr(sandbox_service, "init_providers_and_managers", lambda: ({}, {"daytona_selfhost": manager}))
    monkeypatch.setattr(sandbox_service, "load_all_sandbox_runtimes", lambda _managers: runtimes)

    payload = sandbox_service.mutate_sandbox_runtime(
        runtime_id="sandbox-1",
        action="pause",
        provider_hint="daytona_selfhost",
    )

    assert payload["ok"] is True
    assert payload["mode"] == "manager_runtime"
    assert payload[LOWER_RUNTIME_KEY] == "lease-1"
    assert manager.sandbox_runtime.paused == [(manager.provider, "api")]
