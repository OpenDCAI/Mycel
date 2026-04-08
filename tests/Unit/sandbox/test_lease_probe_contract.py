from pathlib import Path
from types import SimpleNamespace

import pytest

from sandbox.lease import lease_from_row


class _FakeProvider:
    name = "daytona_selfhost"

    def get_capability(self):
        return SimpleNamespace(supports_status_probe=True)

    def create_session(self, context_id=None, thread_id=None):
        return SimpleNamespace(session_id="instance-created")


class _FakeLeaseRepo:
    def __init__(self) -> None:
        self.adopt_calls: list[tuple[str, str, str, str]] = []
        self._row = {
            "lease_id": "lease-1",
            "provider_name": "daytona_selfhost",
            "recipe_id": None,
            "recipe_json": None,
            "workspace_key": None,
            "current_instance_id": None,
            "instance_created_at": None,
            "desired_state": "running",
            "observed_state": "detached",
            "version": 0,
            "observed_at": "2026-04-08T00:00:00+00:00",
            "last_error": None,
            "needs_refresh": 0,
            "refresh_hint_at": None,
            "status": "active",
            "volume_id": None,
            "created_at": "2026-04-08T00:00:00+00:00",
            "updated_at": "2026-04-08T00:00:00+00:00",
            "_instance": None,
        }

    def get(self, lease_id: str):
        if lease_id != "lease-1":
            return None
        return dict(self._row)

    def adopt_instance(self, *, lease_id: str, provider_name: str, instance_id: str, status: str = "unknown"):
        self.adopt_calls.append((lease_id, provider_name, instance_id, status))
        self._row = {
            **self._row,
            "current_instance_id": instance_id,
            "instance_created_at": "2026-04-08T00:00:01+00:00",
            "desired_state": "running",
            "observed_state": status,
            "version": 1,
            "observed_at": "2026-04-08T00:00:01+00:00",
            "needs_refresh": 1,
            "refresh_hint_at": "2026-04-08T00:00:01+00:00",
            "_instance": {
                "instance_id": instance_id,
                "lease_id": lease_id,
                "provider_session_id": instance_id,
                "status": status,
                "created_at": "2026-04-08T00:00:01+00:00",
                "last_seen_at": "2026-04-08T00:00:01+00:00",
            },
        }
        return dict(self._row)

    def close(self) -> None:
        return None


def test_ensure_active_instance_persists_strategy_lease_before_probe_failure(monkeypatch):
    repo = _FakeLeaseRepo()
    lease = lease_from_row(repo.get("lease-1"), Path("/tmp/fake-sandbox.db"))

    monkeypatch.setenv("LEON_STORAGE_STRATEGY", "supabase")
    monkeypatch.setattr("sandbox.lease._make_lease_repo", lambda db_path=None: repo)

    def _explode_probe(**_kwargs):
        raise RuntimeError("snapshot fk boom")

    monkeypatch.setattr("sandbox.resource_snapshot.probe_and_upsert_for_instance", _explode_probe)

    with pytest.raises(RuntimeError, match="snapshot fk boom"):
        lease.ensure_active_instance(_FakeProvider())

    assert repo.adopt_calls == [("lease-1", "daytona_selfhost", "instance-created", "running")]
    assert lease.get_instance() is not None
    assert lease.get_instance().instance_id == "instance-created"
