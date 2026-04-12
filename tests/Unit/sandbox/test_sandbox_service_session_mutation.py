from pathlib import Path

from backend.web.services import sandbox_service


class _FakeLeaseStore:
    def __init__(self):
        self.adopted = []
        self.deleted = []

    def adopt_instance(self, **kwargs):
        self.adopted.append(kwargs)
        return {
            "lease_id": kwargs["lease_id"],
            "provider_name": kwargs["provider_name"],
            "desired_state": "running",
            "observed_state": kwargs["status"],
            "current_instance_id": kwargs["instance_id"],
            "volume_id": None,
        }

    def delete(self, lease_id: str):
        self.deleted.append(lease_id)
        return True


class _FakeLease:
    def __init__(self, lease_id: str):
        self.lease_id = lease_id
        self.destroyed = False

    def destroy_instance(self, _provider, *, source):
        self.destroyed = source == "api"


class _FakeManager:
    def __init__(self):
        self.db_path = Path("/tmp/sandbox.db")
        self.provider = object()
        self.lease_store = _FakeLeaseStore()
        self.lease = None

    def get_lease(self, _lease_id):
        return None


def test_mutate_sandbox_session_adopts_provider_orphan_without_repo_db_path(monkeypatch):
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

    def _lease_from_row(_row, db_path):
        assert db_path == manager.db_path
        manager.lease = _FakeLease(_row["lease_id"])
        return manager.lease

    monkeypatch.setattr("sandbox.lease.lease_from_row", _lease_from_row)

    payload = sandbox_service.mutate_sandbox_session(
        session_id="sandbox-1",
        action="destroy",
        provider_hint="daytona_selfhost",
    )

    assert payload["ok"] is True
    assert payload["mode"] == "manager_lease"
    assert payload["lease_id"].startswith("lease-adopt-")
    assert manager.lease is not None
    assert manager.lease.destroyed is True
    assert manager.lease_store.deleted == [payload["lease_id"]]
