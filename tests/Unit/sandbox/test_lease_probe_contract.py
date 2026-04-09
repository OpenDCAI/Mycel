from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

import sandbox.lease as sandbox_lease
from sandbox.lease import lease_from_row

DEFAULT_SANDBOX_DB = Path("/tmp/fake-sandbox.db")


def _bind_default_sandbox_db(monkeypatch: pytest.MonkeyPatch, path: Path = DEFAULT_SANDBOX_DB) -> Path:
    monkeypatch.setattr(
        "sandbox.lease.resolve_sandbox_db_path",
        lambda db_path=None: path if db_path is None else Path(db_path),
    )
    return path


class _FakeProvider:
    name = "daytona_selfhost"

    def get_capability(self):
        return SimpleNamespace(supports_status_probe=True, can_destroy=True, can_pause=True, can_resume=True)

    def create_session(self, context_id=None, thread_id=None):
        return SimpleNamespace(session_id="instance-created")

    def get_session_status(self, _instance_id: str) -> str:
        return "running"

    def destroy_session(self, _instance_id: str) -> bool:
        return True

    def pause_session(self, _instance_id: str) -> bool:
        return True

    def resume_session(self, _instance_id: str) -> bool:
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

    def mark_needs_refresh(self, lease_id: str, *, hint_at) -> dict[str, object]:
        return self.persist_metadata(
            lease_id=lease_id,
            recipe_id=self._row.get("recipe_id"),
            recipe_json=self._row.get("recipe_json"),
            desired_state=str(self._row["desired_state"]),
            observed_state=str(self._row["observed_state"]),
            version=int(self._row["version"]) + 1,
            observed_at=self._row.get("observed_at"),
            last_error=self._row.get("last_error"),
            needs_refresh=True,
            refresh_hint_at=hint_at.isoformat(),
            status=str(self._row["status"]),
        )

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


def test_use_supabase_storage_defaults_true_when_strategy_missing_with_runtime_config(monkeypatch):
    monkeypatch.delenv("LEON_STORAGE_STRATEGY", raising=False)
    monkeypatch.setenv("LEON_SUPABASE_CLIENT_FACTORY", "tests.fake:create_client")

    assert sandbox_lease._use_supabase_storage() is True


def test_use_supabase_storage_defaults_false_when_strategy_missing_and_runtime_config_missing(monkeypatch):
    monkeypatch.delenv("LEON_STORAGE_STRATEGY", raising=False)
    monkeypatch.delenv("LEON_SUPABASE_CLIENT_FACTORY", raising=False)

    assert sandbox_lease._use_supabase_storage() is False


def test_mark_needs_refresh_without_strategy_env_uses_strategy_repo_when_runtime_config_exists(monkeypatch):
    monkeypatch.delenv("LEON_STORAGE_STRATEGY", raising=False)
    monkeypatch.setenv("LEON_SUPABASE_CLIENT_FACTORY", "tests.fake:create_client")
    repo = _FakeLeaseRepo()
    default_db = _bind_default_sandbox_db(monkeypatch)
    lease = lease_from_row(repo.get("lease-1"), default_db)
    hint_at = datetime.fromisoformat("2026-04-09T00:00:00+00:00")

    monkeypatch.setattr("sandbox.lease._make_lease_repo", lambda db_path=None: repo)
    monkeypatch.setattr("sandbox.lease._connect", lambda _db_path: (_ for _ in ()).throw(AssertionError("should not touch sqlite")))

    lease.mark_needs_refresh(hint_at=hint_at)

    assert len(repo.persist_calls) == 1
    persisted = repo.persist_calls[0]
    assert persisted["lease_id"] == "lease-1"
    assert persisted["needs_refresh"] is True
    assert persisted["refresh_hint_at"] == hint_at.isoformat()


def test_mark_needs_refresh_without_strategy_env_keeps_local_sqlite_when_runtime_config_missing(monkeypatch):
    monkeypatch.delenv("LEON_STORAGE_STRATEGY", raising=False)
    monkeypatch.delenv("LEON_SUPABASE_CLIENT_FACTORY", raising=False)
    default_db = _bind_default_sandbox_db(monkeypatch)
    lease = lease_from_row(_FakeLeaseRepo().get("lease-1"), default_db)
    hint_at = datetime.fromisoformat("2026-04-09T00:00:00+00:00")
    seen_db_paths: list[Path] = []

    class _Conn:
        def execute(self, *_args, **_kwargs):
            return None

        def commit(self) -> None:
            return None

        def rollback(self) -> None:
            return None

        def close(self) -> None:
            return None

    monkeypatch.setattr(
        "sandbox.lease._connect",
        lambda db_path: seen_db_paths.append(db_path) or _Conn(),
    )

    lease.mark_needs_refresh(hint_at=hint_at)

    assert seen_db_paths == [default_db]


def test_ensure_active_instance_persists_strategy_lease_before_probe_failure(monkeypatch):
    repo = _FakeLeaseRepo()
    repo._row = {
        **repo._row,
        "current_instance_id": None,
        "instance_created_at": None,
        "observed_state": "detached",
        "_instance": None,
    }
    lease = lease_from_row(repo.get("lease-1"), _bind_default_sandbox_db(monkeypatch))

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
    lease = lease_from_row(repo.get("lease-1"), _bind_default_sandbox_db(monkeypatch))

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
    lease = lease_from_row(repo.get("lease-1"), _bind_default_sandbox_db(monkeypatch))

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
    lease = lease_from_row(repo.get("lease-1"), _bind_default_sandbox_db(monkeypatch))

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
    lease = lease_from_row(repo.get("lease-1"), _bind_default_sandbox_db(monkeypatch))

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


def test_destroy_instance_strategy_path_reloads_under_lock(monkeypatch):
    repo = _FakeLeaseRepo()
    event_repo = _FakeProviderEventRepo()
    lease = lease_from_row(repo.get("lease-1"), _bind_default_sandbox_db(monkeypatch))
    order: list[str] = []

    class _OrderedProvider(_FakeProvider):
        def destroy_session(self, _instance_id: str) -> bool:
            order.append("provider.destroy")
            return True

    @contextmanager
    def _fake_lock():
        order.append("lock.enter")
        try:
            yield
        finally:
            order.append("lock.exit")

    monkeypatch.setenv("LEON_STORAGE_STRATEGY", "supabase")
    monkeypatch.setattr("sandbox.lease._make_lease_repo", lambda db_path=None: repo)
    monkeypatch.setattr("sandbox.lease._make_provider_event_repo", lambda: event_repo)
    monkeypatch.setattr("sandbox.lease._connect", lambda _db_path: (_ for _ in ()).throw(AssertionError("should not touch sqlite")))
    monkeypatch.setattr(lease, "_instance_lock", lambda: _fake_lock())
    monkeypatch.setattr(lease, "_reload_from_storage", lambda: order.append("reload"))

    lease.destroy_instance(_OrderedProvider(), source="api")

    assert order[:3] == ["lock.enter", "reload", "provider.destroy"]
    assert order[-1] == "lock.exit"


def test_destroy_instance_records_strategy_provider_error_on_failure(monkeypatch):
    repo = _FakeLeaseRepo()
    event_repo = _FakeProviderEventRepo()
    lease = lease_from_row(repo.get("lease-1"), _bind_default_sandbox_db(monkeypatch))

    class _FailingDestroyProvider(_FakeProvider):
        def destroy_session(self, _instance_id: str) -> bool:
            raise RuntimeError("provider boom")

    monkeypatch.setenv("LEON_STORAGE_STRATEGY", "supabase")
    monkeypatch.setattr("sandbox.lease._make_lease_repo", lambda db_path=None: repo)
    monkeypatch.setattr("sandbox.lease._make_provider_event_repo", lambda: event_repo)
    monkeypatch.setattr("sandbox.lease._connect", lambda _db_path: (_ for _ in ()).throw(AssertionError("should not touch sqlite")))

    with pytest.raises(RuntimeError, match="Failed to destroy lease lease-1: provider boom"):
        lease.destroy_instance(_FailingDestroyProvider(), source="api")

    assert len(repo.persist_calls) == 1
    call = repo.persist_calls[0]
    assert call["last_error"] == "Failed to destroy lease lease-1: provider boom"
    assert call["needs_refresh"] is True
    assert call["status"] == "active"
    assert event_repo.record_calls == [
        {
            "provider_name": "daytona_selfhost",
            "instance_id": "inst-1",
            "event_type": "provider.error",
            "payload": {"error": "Failed to destroy lease lease-1: provider boom", "source": "api.destroy"},
            "matched_lease_id": "lease-1",
        }
    ]


def test_destroy_instance_preserves_destroy_state_when_strategy_write_fails(monkeypatch):
    repo = _FakeLeaseRepo()
    event_repo = _FakeProviderEventRepo()
    lease = lease_from_row(repo.get("lease-1"), _bind_default_sandbox_db(monkeypatch))

    class _WriteFailRepo(_FakeLeaseRepo):
        def observe_status(self, *, lease_id: str, status: str, observed_at):
            raise RuntimeError("write boom")

    class _OrderedProvider(_FakeProvider):
        def __init__(self) -> None:
            self.destroy_calls: list[str] = []

        def destroy_session(self, instance_id: str) -> bool:
            self.destroy_calls.append(instance_id)
            return True

    write_fail_repo = _WriteFailRepo()
    provider = _OrderedProvider()

    monkeypatch.setenv("LEON_STORAGE_STRATEGY", "supabase")
    monkeypatch.setattr("sandbox.lease._make_lease_repo", lambda db_path=None: write_fail_repo)
    monkeypatch.setattr("sandbox.lease._make_provider_event_repo", lambda: event_repo)
    monkeypatch.setattr("sandbox.lease._connect", lambda _db_path: (_ for _ in ()).throw(AssertionError("should not touch sqlite")))

    with pytest.raises(RuntimeError, match="write boom"):
        lease.destroy_instance(provider, source="api")

    assert provider.destroy_calls == ["inst-1"]
    assert len(write_fail_repo.persist_calls) == 1
    call = write_fail_repo.persist_calls[0]
    assert call["desired_state"] == "destroyed"
    assert call["observed_state"] == "detached"
    assert call["status"] == "expired"
    assert call["last_error"] == "write boom"
    assert call["needs_refresh"] is True


def test_destroy_instance_bumps_version_again_when_event_write_fails(monkeypatch):
    repo = _FakeLeaseRepo()
    lease = lease_from_row(repo.get("lease-1"), _bind_default_sandbox_db(monkeypatch))

    class _EventFailRepo(_FakeProviderEventRepo):
        def record(
            self,
            *,
            provider_name: str,
            instance_id: str,
            event_type: str,
            payload: dict[str, object],
            matched_lease_id: str | None,
        ) -> None:
            if event_type == "intent.destroy":
                raise RuntimeError("event boom")
            super().record(
                provider_name=provider_name,
                instance_id=instance_id,
                event_type=event_type,
                payload=payload,
                matched_lease_id=matched_lease_id,
            )

    monkeypatch.setenv("LEON_STORAGE_STRATEGY", "supabase")
    monkeypatch.setattr("sandbox.lease._make_lease_repo", lambda db_path=None: repo)
    monkeypatch.setattr("sandbox.lease._make_provider_event_repo", lambda: _EventFailRepo())
    monkeypatch.setattr("sandbox.lease._connect", lambda _db_path: (_ for _ in ()).throw(AssertionError("should not touch sqlite")))

    with pytest.raises(RuntimeError, match="event boom"):
        lease.destroy_instance(_FakeProvider(), source="api")

    assert len(repo.persist_calls) == 2
    assert repo.persist_calls[0]["version"] == 1
    assert repo.persist_calls[-1]["version"] == 2
    assert repo.persist_calls[-1]["desired_state"] == "destroyed"
    assert repo.persist_calls[-1]["observed_state"] == "detached"


def test_pause_instance_uses_strategy_pause_transition(monkeypatch):
    repo = _FakeLeaseRepo()
    event_repo = _FakeProviderEventRepo()
    lease = lease_from_row(repo.get("lease-1"), _bind_default_sandbox_db(monkeypatch))

    monkeypatch.setenv("LEON_STORAGE_STRATEGY", "supabase")
    monkeypatch.setattr("sandbox.lease._make_lease_repo", lambda db_path=None: repo)
    monkeypatch.setattr("sandbox.lease._make_provider_event_repo", lambda: event_repo)
    monkeypatch.setattr("sandbox.lease._connect", lambda _db_path: (_ for _ in ()).throw(AssertionError("should not touch sqlite")))

    lease.pause_instance(_FakeProvider(), source="api")

    assert repo.observe_calls == [
        {
            "lease_id": "lease-1",
            "status": "paused",
            "observed_at": repo.observe_calls[0]["observed_at"],
        }
    ]
    assert len(repo.persist_calls) == 1
    persist = repo.persist_calls[0]
    assert persist["desired_state"] == "paused"
    assert persist["observed_state"] == "paused"
    assert persist["status"] == "active"
    assert persist["needs_refresh"] is False
    assert event_repo.record_calls == [
        {
            "provider_name": "daytona_selfhost",
            "instance_id": "inst-1",
            "event_type": "intent.pause",
            "payload": {"instance_id": "inst-1", "source": "api"},
            "matched_lease_id": "lease-1",
        }
    ]


def test_resume_instance_uses_strategy_resume_transition(monkeypatch):
    repo = _FakeLeaseRepo()
    repo._row = {
        **repo._row,
        "desired_state": "paused",
        "observed_state": "paused",
        "_instance": {
            **repo._row["_instance"],
            "status": "paused",
        },
    }
    event_repo = _FakeProviderEventRepo()
    lease = lease_from_row(repo.get("lease-1"), _bind_default_sandbox_db(monkeypatch))

    monkeypatch.setenv("LEON_STORAGE_STRATEGY", "supabase")
    monkeypatch.setattr("sandbox.lease._make_lease_repo", lambda db_path=None: repo)
    monkeypatch.setattr("sandbox.lease._make_provider_event_repo", lambda: event_repo)
    monkeypatch.setattr("sandbox.lease._connect", lambda _db_path: (_ for _ in ()).throw(AssertionError("should not touch sqlite")))

    lease.resume_instance(_FakeProvider(), source="api")

    assert repo.observe_calls == [
        {
            "lease_id": "lease-1",
            "status": "running",
            "observed_at": repo.observe_calls[0]["observed_at"],
        }
    ]
    assert len(repo.persist_calls) == 1
    persist = repo.persist_calls[0]
    assert persist["desired_state"] == "running"
    assert persist["observed_state"] == "running"
    assert persist["status"] == "active"
    assert persist["needs_refresh"] is False
    assert event_repo.record_calls == [
        {
            "provider_name": "daytona_selfhost",
            "instance_id": "inst-1",
            "event_type": "intent.resume",
            "payload": {"instance_id": "inst-1", "source": "api"},
            "matched_lease_id": "lease-1",
        }
    ]


def test_pause_instance_preserves_paused_state_when_event_write_fails(monkeypatch):
    repo = _FakeLeaseRepo()
    lease = lease_from_row(repo.get("lease-1"), _bind_default_sandbox_db(monkeypatch))

    class _EventFailRepo(_FakeProviderEventRepo):
        def record(
            self,
            *,
            provider_name: str,
            instance_id: str,
            event_type: str,
            payload: dict[str, object],
            matched_lease_id: str | None,
        ) -> None:
            if event_type == "intent.pause":
                raise RuntimeError("event boom")
            super().record(
                provider_name=provider_name,
                instance_id=instance_id,
                event_type=event_type,
                payload=payload,
                matched_lease_id=matched_lease_id,
            )

    monkeypatch.setenv("LEON_STORAGE_STRATEGY", "supabase")
    monkeypatch.setattr("sandbox.lease._make_lease_repo", lambda db_path=None: repo)
    monkeypatch.setattr("sandbox.lease._make_provider_event_repo", lambda: _EventFailRepo())
    monkeypatch.setattr("sandbox.lease._connect", lambda _db_path: (_ for _ in ()).throw(AssertionError("should not touch sqlite")))

    with pytest.raises(RuntimeError, match="event boom"):
        lease.pause_instance(_FakeProvider(), source="api")

    assert len(repo.persist_calls) == 2
    assert repo.persist_calls[0]["version"] == 1
    assert repo.persist_calls[-1]["version"] == 2
    assert repo.persist_calls[-1]["desired_state"] == "paused"
    assert repo.persist_calls[-1]["observed_state"] == "paused"
    assert repo.persist_calls[-1]["last_error"] == "event boom"
    assert repo.persist_calls[-1]["needs_refresh"] is True
