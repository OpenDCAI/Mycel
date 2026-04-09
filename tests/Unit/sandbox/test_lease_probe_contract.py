from pathlib import Path
from types import SimpleNamespace

import pytest

from sandbox.lease import lease_from_row


class _FakeProvider:
    name = "daytona_selfhost"

    def get_capability(self):
        return SimpleNamespace(supports_status_probe=True, can_destroy=True)

    def create_session(self, context_id=None, thread_id=None):
        return SimpleNamespace(session_id="instance-created")

    def get_session_status(self, _instance_id: str) -> str:
        return "running"

    def destroy_session(self, _instance_id: str) -> bool:
        return True


class _FakeLeaseRepo:
    def __init__(self) -> None:
        self.adopt_calls: list[tuple[str, str, str, str]] = []
        self.persist_calls: list[dict[str, object]] = []
        self.observe_calls: list[dict[str, object]] = []
        self._row = {
            "lease_id": "lease-1",
            "provider_name": "daytona_selfhost",
            "recipe_id": None,
            "recipe_json": None,
            "workspace_key": None,
            "current_instance_id": "inst-1",
            "instance_created_at": "2026-04-08T00:00:00+00:00",
            "desired_state": "running",
            "observed_state": "running",
            "version": 0,
            "observed_at": "2026-04-08T00:00:00+00:00",
            "last_error": None,
            "needs_refresh": 0,
            "refresh_hint_at": None,
            "status": "active",
            "volume_id": None,
            "created_at": "2026-04-08T00:00:00+00:00",
            "updated_at": "2026-04-08T00:00:00+00:00",
            "_instance": {
                "instance_id": "inst-1",
                "lease_id": "lease-1",
                "provider_session_id": "inst-1",
                "status": "running",
                "created_at": "2026-04-08T00:00:00+00:00",
                "last_seen_at": "2026-04-08T00:00:00+00:00",
            },
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

    def persist_metadata(
        self,
        *,
        lease_id: str,
        recipe_id,
        recipe_json,
        desired_state: str,
        observed_state: str,
        version: int,
        observed_at,
        last_error,
        needs_refresh: bool,
        refresh_hint_at,
        status: str,
    ):
        self.persist_calls.append(
            {
                "lease_id": lease_id,
                "recipe_id": recipe_id,
                "recipe_json": recipe_json,
                "desired_state": desired_state,
                "observed_state": observed_state,
                "version": version,
                "observed_at": observed_at,
                "last_error": last_error,
                "needs_refresh": needs_refresh,
                "refresh_hint_at": refresh_hint_at,
                "status": status,
            }
        )
        self._row = {
            **self._row,
            "recipe_id": recipe_id,
            "recipe_json": recipe_json,
            "desired_state": desired_state,
            "observed_state": observed_state,
            "version": version,
            "observed_at": observed_at,
            "last_error": last_error,
            "needs_refresh": int(needs_refresh),
            "refresh_hint_at": refresh_hint_at,
            "status": status,
        }
        return dict(self._row)

    def observe_status(
        self,
        *,
        lease_id: str,
        status: str,
        observed_at,
    ):
        self.observe_calls.append(
            {
                "lease_id": lease_id,
                "status": status,
                "observed_at": observed_at,
            }
        )
        self._row = {
            **self._row,
            "observed_state": status,
            "version": int(self._row["version"]) + 1,
            "observed_at": observed_at,
            "last_error": None,
            "needs_refresh": 0,
            "refresh_hint_at": None,
            "status": "active",
            "_instance": {
                **(self._row["_instance"] or {}),
                "status": status,
                "last_seen_at": observed_at,
            },
        }
        return dict(self._row)

    def close(self) -> None:
        return None


class _FakeProviderEventRepo:
    def __init__(self) -> None:
        self.record_calls: list[dict[str, object]] = []

    def record(
        self,
        *,
        provider_name: str,
        instance_id: str,
        event_type: str,
        payload: dict[str, object],
        matched_lease_id: str | None,
    ) -> None:
        self.record_calls.append(
            {
                "provider_name": provider_name,
                "instance_id": instance_id,
                "event_type": event_type,
                "payload": payload,
                "matched_lease_id": matched_lease_id,
            }
        )

    def close(self) -> None:
        return None


def test_sandbox_lease_no_longer_imports_storage_factory() -> None:
    lease_source = Path("sandbox/lease.py").read_text(encoding="utf-8")

    assert "backend.web.core.storage_factory" not in lease_source
    assert "sandbox.control_plane_repos" in lease_source
    assert "SQLiteLeaseRepo" not in lease_source


def test_ensure_active_instance_persists_strategy_lease_before_probe_failure(monkeypatch):
    repo = _FakeLeaseRepo()
    repo._row = {
        **repo._row,
        "current_instance_id": None,
        "instance_created_at": None,
        "observed_state": "detached",
        "_instance": None,
    }
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


def test_record_provider_error_persists_strategy_metadata(monkeypatch):
    repo = _FakeLeaseRepo()
    event_repo = _FakeProviderEventRepo()
    lease = lease_from_row(repo.get("lease-1"), Path("/tmp/fake-sandbox.db"))

    monkeypatch.setenv("LEON_STORAGE_STRATEGY", "supabase")
    monkeypatch.setattr("sandbox.lease._make_lease_repo", lambda db_path=None: repo)
    monkeypatch.setattr("sandbox.lease._make_provider_event_repo", lambda: event_repo)

    lease._record_provider_error("provider boom")

    assert len(repo.persist_calls) == 1
    call = repo.persist_calls[0]
    assert call["lease_id"] == "lease-1"
    assert call["last_error"] == "provider boom"
    assert call["needs_refresh"] is True
    assert call["status"] == "active"
    assert call["version"] == 1
    assert event_repo.record_calls == [
        {
            "provider_name": "daytona_selfhost",
            "instance_id": "inst-1",
            "event_type": "provider.error",
            "payload": {"error": "provider boom", "source": "provider"},
            "matched_lease_id": "lease-1",
        }
    ]


def test_refresh_instance_status_uses_strategy_observe_status_transition(monkeypatch):
    repo = _FakeLeaseRepo()
    event_repo = _FakeProviderEventRepo()
    lease = lease_from_row(repo.get("lease-1"), Path("/tmp/fake-sandbox.db"))

    monkeypatch.setenv("LEON_STORAGE_STRATEGY", "supabase")
    monkeypatch.setattr("sandbox.lease._make_lease_repo", lambda db_path=None: repo)
    monkeypatch.setattr("sandbox.lease._make_provider_event_repo", lambda: event_repo)
    monkeypatch.setattr("sandbox.lease._connect", lambda _db_path: (_ for _ in ()).throw(AssertionError("should not touch sqlite")))

    observed = lease.refresh_instance_status(_FakeProvider(), force=True)

    assert observed == "running"
    assert repo.observe_calls
    assert repo.observe_calls[0]["lease_id"] == "lease-1"
    assert repo.observe_calls[0]["status"] == "running"
    assert event_repo.record_calls == [
        {
            "provider_name": "daytona_selfhost",
            "instance_id": "inst-1",
            "event_type": "observe.status",
            "payload": {"status": "running", "instance_id": "inst-1"},
            "matched_lease_id": "lease-1",
        }
    ]


def test_refresh_instance_status_records_strategy_provider_error_event(monkeypatch):
    repo = _FakeLeaseRepo()
    event_repo = _FakeProviderEventRepo()
    lease = lease_from_row(repo.get("lease-1"), Path("/tmp/fake-sandbox.db"))

    class _FailingProvider(_FakeProvider):
        def get_session_status(self, _instance_id: str) -> str:
            raise RuntimeError("provider boom")

    monkeypatch.setenv("LEON_STORAGE_STRATEGY", "supabase")
    monkeypatch.setattr("sandbox.lease._make_lease_repo", lambda db_path=None: repo)
    monkeypatch.setattr("sandbox.lease._make_provider_event_repo", lambda: event_repo)
    monkeypatch.setattr("sandbox.lease._connect", lambda _db_path: (_ for _ in ()).throw(AssertionError("should not touch sqlite")))

    observed = lease.refresh_instance_status(_FailingProvider(), force=True)

    assert observed == "running"
    assert len(repo.persist_calls) == 1
    call = repo.persist_calls[0]
    assert call["last_error"] == "provider boom"
    assert call["needs_refresh"] is True
    assert event_repo.record_calls == [
        {
            "provider_name": "daytona_selfhost",
            "instance_id": "inst-1",
            "event_type": "provider.error",
            "payload": {"error": "provider boom", "source": "read.status"},
            "matched_lease_id": "lease-1",
        }
    ]


def test_destroy_instance_uses_strategy_destroy_transition(monkeypatch):
    repo = _FakeLeaseRepo()
    event_repo = _FakeProviderEventRepo()
    lease = lease_from_row(repo.get("lease-1"), Path("/tmp/fake-sandbox.db"))

    monkeypatch.setenv("LEON_STORAGE_STRATEGY", "supabase")
    monkeypatch.setattr("sandbox.lease._make_lease_repo", lambda db_path=None: repo)
    monkeypatch.setattr("sandbox.lease._make_provider_event_repo", lambda: event_repo)
    monkeypatch.setattr("sandbox.lease._connect", lambda _db_path: (_ for _ in ()).throw(AssertionError("should not touch sqlite")))

    lease.destroy_instance(_FakeProvider(), source="api")

    assert repo.observe_calls == [
        {
            "lease_id": "lease-1",
            "status": "detached",
            "observed_at": repo.observe_calls[0]["observed_at"],
        }
    ]
    assert len(repo.persist_calls) == 1
    persist = repo.persist_calls[0]
    assert persist["desired_state"] == "destroyed"
    assert persist["observed_state"] == "detached"
    assert persist["status"] == "expired"
    assert persist["needs_refresh"] is False
    assert event_repo.record_calls == [
        {
            "provider_name": "daytona_selfhost",
            "instance_id": "inst-1",
            "event_type": "intent.destroy",
            "payload": {"instance_id": "inst-1", "source": "api"},
            "matched_lease_id": "lease-1",
        }
    ]
