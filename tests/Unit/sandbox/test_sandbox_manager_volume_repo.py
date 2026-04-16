import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

import sandbox.manager as sandbox_manager_module
from config.user_paths import user_home_path
from sandbox.manager import SandboxManager
from sandbox.providers.local import LocalSessionProvider
from sandbox.volume_source import HostVolume, deserialize_volume_source


class _FakeVolumeRepo:
    def __init__(self, source: dict[str, str]) -> None:
        self._source = source
        self.closed = False
        self.requested_ids: list[str] = []
        self.created: list[tuple[str, str | None]] = []
        self.deleted: list[str] = []

    def get(self, volume_id: str) -> dict[str, str] | None:
        self.requested_ids.append(volume_id)
        if self.created and volume_id == self.created[-1][0]:
            return {"source": json.dumps(self._source)}
        return {"source": json.dumps(self._source)}

    def create(self, volume_id: str, source_json: str, name: str | None, created_at: str) -> None:
        self.created.append((volume_id, name))
        self._source = json.loads(source_json)

    def delete(self, volume_id: str) -> bool:
        self.deleted.append(volume_id)
        return True

    def close(self) -> None:
        self.closed = True


class _FakeVolume:
    def __init__(self) -> None:
        self.mount_calls: list[tuple[str, str]] = []
        self.mount_sources: list[Path | None] = []
        self.upload_calls: list[tuple[str, str, Path, str]] = []
        self.download_calls: list[tuple[str, str, Path, str]] = []
        self.cleared: list[str] = []

    def resolve_mount_path(self) -> str:
        return "/workspace"

    def mount(self, thread_id: str, source_path: Path | None, remote_path: str) -> None:
        self.mount_calls.append((thread_id, remote_path))
        self.mount_sources.append(source_path)

    def mount_managed_volume(self, thread_id: str, volume_name: str, remote_path: str) -> None:
        self.mount_calls.append((thread_id, remote_path))

    def sync_upload(self, thread_id: str, session_id: str, source_path: Path, remote_path: str, files=None) -> None:
        self.upload_calls.append((thread_id, session_id, source_path, remote_path))

    def sync_download(self, thread_id: str, session_id: str, source_path: Path, remote_path: str) -> None:
        self.download_calls.append((thread_id, session_id, source_path, remote_path))

    def clear_sync_state(self, thread_id: str) -> None:
        self.cleared.append(thread_id)


class _FakeThreadRepo:
    def __init__(self, row):
        self._row = row
        self.closed = False

    def get_by_id(self, _thread_id: str):
        return self._row

    def close(self) -> None:
        self.closed = True


class _FakeUpdateRepo:
    def __init__(self) -> None:
        self.updated: list[tuple[str, str]] = []
        self.closed = False

    def update_source(self, volume_id: str, source_json: str) -> None:
        self.updated.append((volume_id, source_json))

    def close(self) -> None:
        self.closed = True


class _FakeLeaseStore:
    pass


class _FakeTerminalRepo:
    def __init__(self, row: dict[str, Any] | None = None) -> None:
        self._row = row
        self.closed = False
        self.requested_lease_ids: list[str] = []

    def get_latest_by_lease(self, lease_id: str):
        self.requested_lease_ids.append(lease_id)
        return self._row

    def close(self) -> None:
        self.closed = True


class _FakeBindTerminalRepo:
    def __init__(self, latest_by_lease: dict[str, Any] | None = None, active_by_thread: dict[str, Any] | None = None) -> None:
        self._latest_by_lease = latest_by_lease
        self._active_by_thread = active_by_thread or {}
        self.closed = False
        self.requested_lease_ids: list[str] = []
        self.requested_active_threads: list[str] = []
        self.created: list[dict[str, Any]] = []

    def get_latest_by_lease(self, lease_id: str):
        self.requested_lease_ids.append(lease_id)
        return self._latest_by_lease

    def get_active(self, thread_id: str):
        self.requested_active_threads.append(thread_id)
        return self._active_by_thread.get(thread_id)

    def create(self, *, terminal_id: str, thread_id: str, lease_id: str, initial_cwd: str) -> None:
        self.created.append(
            {
                "terminal_id": terminal_id,
                "thread_id": thread_id,
                "lease_id": lease_id,
                "initial_cwd": initial_cwd,
            }
        )

    def close(self) -> None:
        self.closed = True


class _FakeLeaseRepo:
    def __init__(self, row: dict[str, Any] | None = None) -> None:
        self._row = row
        self.closed = False
        self.requested_ids: list[str] = []
        self.instance_queries: list[tuple[str, str]] = []

    def get(self, lease_id: str):
        self.requested_ids.append(lease_id)
        return self._row

    def find_by_instance(self, *, provider_name: str, instance_id: str):
        self.instance_queries.append((provider_name, instance_id))
        return None

    def close(self) -> None:
        self.closed = True


class _FakeSessionManager:
    def __init__(self, active_rows) -> None:
        self._active_rows = active_rows
        self.deleted: list[tuple[str, str]] = []

    def list_active(self):
        return list(self._active_rows)

    def delete(self, session_id: str, reason: str) -> None:
        self.deleted.append((session_id, reason))


class _FakeDaytonaProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.ready_waits: list[str] = []
        self.deleted_volumes: list[str] = []

    def create_managed_volume(self, volume_id: str, mount_path: str) -> str:
        self.calls.append((volume_id, mount_path))
        return f"leon-volume-{volume_id}"

    def wait_managed_volume_ready(self, volume_name: str) -> None:
        self.ready_waits.append(volume_name)

    def delete_managed_volume(self, volume_name: str) -> None:
        self.deleted_volumes.append(volume_name)


def _new_test_manager() -> Any:
    # @@@nu59-sandbox-manager-harness - these tests intentionally bypass
    # SandboxManager.__init__ and monkey-build partial instances. Treat that
    # object as a test harness, not a fully typed production manager.
    manager = cast(Any, object.__new__(SandboxManager))
    manager.db_path = Path("/tmp/fake-sandbox.db")
    return manager


def test_resolve_existing_lease_cwd_prefers_provider_default_when_no_workspace_truth(monkeypatch):
    lease_repo = _FakeLeaseRepo(row={"lease_id": "lease-1", "provider_name": "local"})

    def build_provider(name: str):
        return SimpleNamespace(default_cwd=f"/providers/{name}") if name == "local" else None

    monkeypatch.setattr(
        sandbox_manager_module,
        "_build_provider_from_name",
        build_provider,
    )

    cwd = sandbox_manager_module.resolve_existing_lease_cwd(
        "lease-1",
        db_path=Path("/tmp/fake-sandbox.db"),
        lease_repo=lease_repo,
    )

    assert cwd == "/providers/local"
    assert lease_repo.requested_ids == ["lease-1"]
    assert lease_repo.closed is False


def test_resolve_existing_lease_cwd_ignores_latest_terminal_cwd_and_prefers_provider_default(monkeypatch):
    lease_repo = _FakeLeaseRepo(row={"lease_id": "lease-1", "provider_name": "local"})
    monkeypatch.setattr(
        sandbox_manager_module,
        "_build_provider_from_name",
        lambda name: SimpleNamespace(default_cwd=f"/providers/{name}"),
    )

    cwd = sandbox_manager_module.resolve_existing_lease_cwd(
        "lease-1",
        db_path=Path("/tmp/fake-sandbox.db"),
        lease_repo=lease_repo,
    )

    assert cwd == "/providers/local"
    assert lease_repo.requested_ids == ["lease-1"]


def test_resolve_existing_lease_cwd_fails_loud_when_provider_default_is_unavailable(monkeypatch):
    lease_repo = _FakeLeaseRepo(row={"lease_id": "lease-1", "provider_name": "missing-provider"})
    monkeypatch.setattr(
        sandbox_manager_module,
        "_build_provider_from_name",
        lambda _name: None,
    )

    with pytest.raises(ValueError, match="provider default cwd is required"):
        sandbox_manager_module.resolve_existing_lease_cwd(
            "lease-1",
            db_path=Path("/tmp/fake-sandbox.db"),
            lease_repo=lease_repo,
        )

    assert lease_repo.requested_ids == ["lease-1"]


def test_bind_thread_to_existing_sandbox_skips_latest_terminal_cwd_when_provider_default_exists(monkeypatch):
    terminal_repo = _FakeBindTerminalRepo(latest_by_lease={"cwd": "/terminal/latest"})
    lease_repo = _FakeLeaseRepo(row={"lease_id": "lease-1", "provider_name": "local"})

    monkeypatch.setattr(
        sandbox_manager_module,
        "_build_provider_from_name",
        lambda name: SimpleNamespace(default_cwd=f"/providers/{name}"),
    )

    initial_cwd, lease = sandbox_manager_module.bind_thread_to_existing_sandbox(
        "thread-1",
        {
            "provider_name": "local",
            "provider_env_id": "env-1",
            "config": {"legacy_lease_id": "legacy-lease"},
        },
        resolve_lease=lambda _lease_id: {"lease_id": "lease-1"},
        db_path=Path("/tmp/fake-sandbox.db"),
        terminal_repo=terminal_repo,
        lease_repo=lease_repo,
    )

    assert initial_cwd == "/providers/local"
    assert lease["lease_id"] == "lease-1"
    assert terminal_repo.created[0]["initial_cwd"] == "/providers/local"


def test_bind_thread_to_existing_thread_lease_requires_parent_workspace_cwd(monkeypatch):
    terminal_repo = _FakeBindTerminalRepo(
        latest_by_lease={"cwd": "/terminal/latest"},
        active_by_thread={"thread-parent": {"lease_id": "lease-1"}},
    )
    lease_repo = _FakeLeaseRepo(row={"lease_id": "lease-1", "provider_name": "local"})

    monkeypatch.setattr(
        sandbox_manager_module,
        "_build_provider_from_name",
        lambda _name: (_ for _ in ()).throw(AssertionError("provider default should stay unused for continuity path")),
    )

    try:
        sandbox_manager_module.bind_thread_to_existing_thread_lease(
            "thread-child",
            "thread-parent",
            db_path=Path("/tmp/fake-sandbox.db"),
            terminal_repo=terminal_repo,
            lease_repo=lease_repo,
        )
    except ValueError as exc:
        assert str(exc) == "thread reuse cwd is required"
    else:
        raise AssertionError("expected bind_thread_to_existing_thread_lease to fail loudly without cwd")


def test_setup_mounts_uses_workspace_sync_source_for_non_daytona_runtime(tmp_path):
    manager = _new_test_manager()
    manager.provider_capability = SimpleNamespace(runtime_kind="agentbay")
    manager.volume = _FakeVolume()
    manager._get_active_terminal = lambda _thread_id: SimpleNamespace(lease_id="lease-1")
    manager._get_lease = lambda _lease_id: SimpleNamespace(volume_id=None)
    manager._resolve_sync_source_path = lambda _thread_id: Path(tmp_path) / "channel-root"
    repo = _FakeVolumeRepo(HostVolume(Path(tmp_path) / "vol").serialize())
    manager._sandbox_volume_repo = lambda: repo

    result = manager._setup_mounts("thread-1")

    assert repo.requested_ids == []
    assert result == {"source_path": Path(tmp_path) / "channel-root", "remote_path": "/workspace"}
    assert manager.volume.mount_calls == [("thread-1", "/workspace")]
    assert manager.volume.mount_sources == [Path(tmp_path) / "channel-root"]


def test_manager_no_longer_exposes_generic_volume_source_helper():
    manager = _new_test_manager()

    assert not hasattr(manager, "resolve_volume_source")


def test_deserialize_historical_daytona_source_downgrades_to_host_volume(tmp_path):
    source = deserialize_volume_source(
        {
            "type": "daytona",
            "staging_path": str(tmp_path / "staging"),
            "volume_name": "leon-volume-volume-1",
        }
    )

    assert isinstance(source, HostVolume)
    assert source.host_path == (tmp_path / "staging").resolve()


def test_setup_mounts_provisions_missing_remote_volume_metadata(monkeypatch, tmp_path):
    manager = _new_test_manager()
    manager.provider_capability = SimpleNamespace(runtime_kind="agentbay")
    manager.volume = _FakeVolume()
    manager._get_active_terminal = lambda _thread_id: SimpleNamespace(lease_id="lease-1")
    manager._resolve_sync_source_path = lambda _thread_id: Path(tmp_path) / "channel-root"
    lease = SimpleNamespace(lease_id="lease-1", volume_id=None)
    manager._get_lease = lambda _lease_id: lease
    manager.lease_store = _FakeLeaseStore()
    repo = _FakeVolumeRepo(HostVolume(Path(tmp_path) / "vol").serialize())
    manager._sandbox_volume_repo = lambda: repo
    monkeypatch.setenv("LEON_SANDBOX_VOLUME_ROOT", str(tmp_path / "volumes"))

    result = manager._setup_mounts("thread-1")

    assert lease.volume_id is None
    assert repo.created == []
    assert repo.requested_ids == []
    assert result == {"source_path": Path(tmp_path) / "channel-root", "remote_path": "/workspace"}
    assert manager.volume.mount_sources == [Path(tmp_path) / "channel-root"]


def test_setup_mounts_daytona_does_not_require_volume_id(monkeypatch, tmp_path):
    manager = _new_test_manager()
    manager.provider_capability = SimpleNamespace(runtime_kind="daytona_pty")
    manager.provider = _FakeDaytonaProvider()
    manager.volume = _FakeVolume()
    manager._get_active_terminal = lambda _thread_id: SimpleNamespace(lease_id="lease-1")
    manager._resolve_sync_source_path = lambda _thread_id: Path(tmp_path) / "channel-root"
    lease = SimpleNamespace(lease_id="lease-1", volume_id=None)
    manager._get_lease = lambda _lease_id: lease
    manager.lease_store = _FakeLeaseStore()
    repo = _FakeVolumeRepo(HostVolume(Path(tmp_path) / "vol").serialize())
    manager._sandbox_volume_repo = lambda: repo
    monkeypatch.setenv("LEON_SANDBOX_VOLUME_ROOT", str(tmp_path / "volumes"))

    result = manager._setup_mounts("thread-1")

    assert repo.created == []
    assert repo.requested_ids == []
    assert result == {"source_path": Path(tmp_path) / "channel-root", "remote_path": "/workspace"}
    assert manager.provider.calls == [("lease-1", "/workspace")]


def test_destroy_thread_resources_daytona_does_not_require_volume_row(tmp_path):
    manager = _new_test_manager()
    provider = _FakeDaytonaProvider()
    manager.provider_capability = SimpleNamespace(runtime_kind="daytona_pty")
    manager.provider = provider
    manager.volume = _FakeVolume()
    deleted_sessions: list[tuple[str, str]] = []
    deleted_terminals: list[str] = []
    destroyed_leases: list[str] = []
    deleted_leases: list[str] = []

    class _MissingDeleteRepo(_FakeVolumeRepo):
        def __init__(self) -> None:
            super().__init__(HostVolume(tmp_path / "staging").serialize())

        def get(self, volume_id: str):
            self.requested_ids.append(volume_id)
            return None

        def delete(self, volume_id: str) -> bool:
            self.deleted.append(volume_id)
            return False

    repo = _MissingDeleteRepo()
    manager._sandbox_volume_repo = lambda: repo

    class _Lease:
        lease_id = "lease-1"
        observed_state = "detached"
        volume_id = "volume-1"

        def get_instance(self):
            return None

        def destroy_instance(self, _provider):
            destroyed_leases.append("lease-1")

    lease = _Lease()
    all_terminals = [{"terminal_id": "term-1", "lease_id": "lease-1", "thread_id": "thread-1"}]
    manager._get_thread_lease = lambda _thread_id: lease
    manager._get_lease = lambda _lease_id: lease
    manager.terminal_store = SimpleNamespace(
        list_by_thread=lambda thread_id: [row for row in all_terminals if row["thread_id"] == thread_id],
        delete=lambda terminal_id: (
            deleted_terminals.append(terminal_id),
            all_terminals.__setitem__(slice(None), [row for row in all_terminals if row["terminal_id"] != terminal_id]),
        ),
        list_all=lambda: list(all_terminals),
        db_path=Path("/tmp/fake-sandbox.db"),
    )
    manager.session_manager = SimpleNamespace(
        delete_thread=lambda thread_id, reason="thread_deleted": deleted_sessions.append((thread_id, reason)),
    )
    manager.lease_store = SimpleNamespace(delete=lambda lease_id: deleted_leases.append(lease_id))

    assert manager.destroy_thread_resources("thread-1") is True
    assert destroyed_leases == ["lease-1"]
    assert provider.deleted_volumes == ["leon-volume-lease-1"]
    assert repo.requested_ids == []
    assert repo.deleted == []
    assert deleted_leases == ["lease-1"]


def test_enforce_idle_timeouts_destroys_when_provider_cannot_pause(monkeypatch):
    manager = _new_test_manager()
    manager.provider = SimpleNamespace(
        name="agentbay",
        get_capability=lambda: SimpleNamespace(can_pause=False, can_destroy=True),
    )
    manager.terminal_store = SimpleNamespace(
        db_path=Path("/tmp/fake-sandbox.db"),
        get_by_id=lambda _terminal_id: {"terminal_id": "term-1", "lease_id": "lease-1"},
    )
    active_rows = [
        {
            "session_id": "sess-1",
            "thread_id": "thread-1",
            "terminal_id": "term-1",
            "lease_id": "lease-1",
            "started_at": "2026-04-04T00:00:00",
            "last_active_at": "2026-04-04T00:00:00",
            "idle_ttl_sec": 1,
            "max_duration_sec": 3600,
            "status": "active",
        }
    ]
    manager.session_manager = _FakeSessionManager(active_rows)
    fake_lease = SimpleNamespace(
        lease_id="lease-1",
        provider_name="agentbay",
        refresh_instance_status=lambda _provider: "running",
        pause_instance=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("pause should not be used")),
        destroy_instance=lambda *_args, **_kwargs: destroy_calls.append(True),
    )
    destroy_calls: list[bool] = []
    manager._get_lease = lambda _lease_id: fake_lease
    manager._terminal_is_busy = lambda _terminal_id: False
    manager._lease_is_busy = lambda _lease_id: False
    monkeypatch.setattr(
        sandbox_manager_module,
        "terminal_from_row",
        lambda _row, _db_path: SimpleNamespace(terminal_id="term-1", lease_id="lease-1"),
    )

    manager.enforce_idle_timeouts()

    assert destroy_calls == [True]
    assert manager.session_manager.deleted == [("sess-1", "idle_timeout")]


def test_enforce_idle_timeouts_accepts_aware_supabase_timestamps():
    manager = _new_test_manager()
    manager.provider = SimpleNamespace(name="daytona_selfhost", get_capability=lambda: SimpleNamespace(can_pause=True, can_destroy=True))
    manager.session_manager = SimpleNamespace(
        list_active=lambda: [
            {
                "session_id": "sess-1",
                "thread_id": "thread-1",
                "started_at": "2099-04-04T00:00:00+00:00",
                "last_active_at": "2099-04-04T00:00:00+00:00",
                "idle_ttl_sec": 3600,
                "max_duration_sec": 7200,
                "status": "active",
            }
        ]
    )

    assert manager.enforce_idle_timeouts() == 0


def test_destroy_thread_resources_skips_local_sync_when_lease_has_no_volume_id():
    manager = _new_test_manager()
    manager.provider_capability = SimpleNamespace(runtime_kind="local")
    manager.provider = SimpleNamespace(name="local")
    manager.volume = _FakeVolume()
    manager._get_thread_lease = lambda _thread_id: lease
    manager._get_lease = lambda _lease_id: lease
    manager._resolve_volume_entry = lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("volume lookup should not happen"))
    manager.terminal_store = SimpleNamespace(
        list_by_thread=lambda _thread_id: [{"terminal_id": "term-1", "lease_id": "lease-1", "thread_id": "thread-1"}],
        delete=lambda _terminal_id: deleted_terminals.append(_terminal_id),
        list_all=lambda: [],
        db_path=Path("/tmp/fake-sandbox.db"),
    )
    manager.session_manager = SimpleNamespace(
        get=lambda _thread_id, _terminal_id: SimpleNamespace(session_id="sess-1"),
        delete=lambda session_id, reason: deleted_sessions.append((session_id, reason)),
        delete_thread=lambda thread_id, reason="thread_deleted": deleted_sessions.append((thread_id, reason)),
    )
    deleted_terminals: list[str] = []
    deleted_sessions: list[tuple[str, str]] = []
    destroy_calls: list[str] = []

    class _Lease:
        lease_id = "lease-1"
        observed_state = "running"
        volume_id = None

        def get_instance(self):
            return SimpleNamespace(instance_id="instance-1")

        def destroy_instance(self, _provider):
            destroy_calls.append("lease-1")

    lease = _Lease()
    manager.lease_store = SimpleNamespace(delete=lambda lease_id: deleted_leases.append(lease_id))
    deleted_leases: list[str] = []

    assert manager.destroy_thread_resources("thread-1") is True
    assert manager.volume.download_calls == []
    assert manager.volume.cleared == ["thread-1"]
    assert deleted_sessions == [("thread-1", "thread_deleted")]
    assert deleted_terminals == ["term-1"]
    assert destroy_calls == ["lease-1"]
    assert deleted_leases == ["lease-1"]


def test_destroy_thread_resources_hard_deletes_thread_chat_sessions_before_terminal_delete():
    manager = _new_test_manager()
    manager.provider_capability = SimpleNamespace(runtime_kind="local")
    manager.provider = SimpleNamespace(name="local")
    manager.volume = _FakeVolume()
    deleted_terminals: list[str] = []
    delete_order: list[str] = []
    destroyed_leases: list[str] = []
    deleted_leases: list[str] = []

    class _Lease:
        lease_id = "lease-1"
        observed_state = "running"
        volume_id = None

        def get_instance(self):
            return SimpleNamespace(instance_id="instance-1")

        def destroy_instance(self, _provider):
            destroyed_leases.append("lease-1")

    lease = _Lease()
    manager._get_thread_lease = lambda _thread_id: lease
    manager._get_lease = lambda _lease_id: lease
    manager._resolve_volume_entry = lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("volume lookup should not happen"))
    manager.terminal_store = SimpleNamespace(
        list_by_thread=lambda _thread_id: [{"terminal_id": "term-1", "lease_id": "lease-1", "thread_id": "thread-1"}],
        delete=lambda terminal_id: (delete_order.append(f"terminal:{terminal_id}"), deleted_terminals.append(terminal_id)),
        list_all=lambda: [],
        db_path=Path("/tmp/fake-sandbox.db"),
    )
    manager.session_manager = SimpleNamespace(
        get=lambda _thread_id, _terminal_id: SimpleNamespace(session_id="sess-1"),
        delete=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("soft delete should not be used")),
        delete_thread=lambda thread_id, reason="thread_deleted": delete_order.append(f"thread:{thread_id}:{reason}"),
    )
    manager.lease_store = SimpleNamespace(delete=lambda lease_id: deleted_leases.append(lease_id))

    assert manager.destroy_thread_resources("thread-1") is True
    assert delete_order == ["thread:thread-1:thread_deleted", "terminal:term-1"]
    assert deleted_terminals == ["term-1"]
    assert destroyed_leases == ["lease-1"]
    assert deleted_leases == ["lease-1"]


def test_destroy_thread_resources_keeps_shared_lease_for_surviving_threads():
    manager = _new_test_manager()
    manager.provider_capability = SimpleNamespace(runtime_kind="local")
    manager.provider = SimpleNamespace(name="local")
    manager.volume = _FakeVolume()
    deleted_sessions: list[tuple[str, str]] = []
    deleted_terminals: list[str] = []
    destroyed_leases: list[str] = []
    deleted_leases: list[str] = []
    all_terminals = [
        {"terminal_id": "term-1", "lease_id": "lease-1", "thread_id": "thread-1"},
        {"terminal_id": "term-2", "lease_id": "lease-1", "thread_id": "thread-2"},
    ]

    class _Lease:
        lease_id = "lease-1"
        observed_state = "detached"
        volume_id = None

        def get_instance(self):
            return None

        def destroy_instance(self, _provider):
            destroyed_leases.append("lease-1")

    lease = _Lease()
    manager._get_thread_lease = lambda _thread_id: lease
    manager._get_lease = lambda _lease_id: lease
    manager._resolve_volume_entry = lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("volume lookup should not happen"))
    manager.terminal_store = SimpleNamespace(
        list_by_thread=lambda thread_id: [row for row in all_terminals if row["thread_id"] == thread_id],
        delete=lambda terminal_id: (
            deleted_terminals.append(terminal_id),
            all_terminals.__setitem__(slice(None), [row for row in all_terminals if row["terminal_id"] != terminal_id]),
        ),
        list_all=lambda: list(all_terminals),
        db_path=Path("/tmp/fake-sandbox.db"),
    )
    manager.session_manager = SimpleNamespace(
        delete_thread=lambda thread_id, reason="thread_deleted": deleted_sessions.append((thread_id, reason)),
    )
    manager.lease_store = SimpleNamespace(delete=lambda lease_id: deleted_leases.append(lease_id))

    assert manager.destroy_thread_resources("thread-1") is True
    assert deleted_sessions == [("thread-1", "thread_deleted")]
    assert deleted_terminals == ["term-1"]
    assert destroyed_leases == []
    assert deleted_leases == []


def test_destroy_thread_resources_deletes_daytona_managed_volume_without_volume_id(tmp_path):
    manager = _new_test_manager()
    provider = _FakeDaytonaProvider()
    manager.provider_capability = SimpleNamespace(runtime_kind="daytona_pty")
    manager.provider = provider
    manager.volume = _FakeVolume()
    deleted_sessions: list[tuple[str, str]] = []
    deleted_terminals: list[str] = []
    destroyed_leases: list[str] = []
    deleted_leases: list[str] = []
    repo = _FakeVolumeRepo(HostVolume(tmp_path / "staging").serialize())
    manager._sandbox_volume_repo = lambda: repo

    class _Lease:
        lease_id = "lease-1"
        observed_state = "detached"
        volume_id = None

        def get_instance(self):
            return None

        def destroy_instance(self, _provider):
            destroyed_leases.append("lease-1")

    lease = _Lease()
    all_terminals = [{"terminal_id": "term-1", "lease_id": "lease-1", "thread_id": "thread-1"}]
    manager._get_thread_lease = lambda _thread_id: lease
    manager._get_lease = lambda _lease_id: lease
    manager.terminal_store = SimpleNamespace(
        list_by_thread=lambda thread_id: [row for row in all_terminals if row["thread_id"] == thread_id],
        delete=lambda terminal_id: (
            deleted_terminals.append(terminal_id),
            all_terminals.__setitem__(slice(None), [row for row in all_terminals if row["terminal_id"] != terminal_id]),
        ),
        list_all=lambda: list(all_terminals),
        db_path=Path("/tmp/fake-sandbox.db"),
    )
    manager.session_manager = SimpleNamespace(
        delete_thread=lambda thread_id, reason="thread_deleted": deleted_sessions.append((thread_id, reason)),
    )
    manager.lease_store = SimpleNamespace(delete=lambda lease_id: deleted_leases.append(lease_id))

    assert manager.destroy_thread_resources("thread-1") is True
    assert destroyed_leases == ["lease-1"]
    assert provider.deleted_volumes == ["leon-volume-lease-1"]
    assert repo.deleted == []
    assert deleted_leases == ["lease-1"]
    assert all_terminals == []


def test_destroy_thread_resources_derives_daytona_volume_name_without_serialized_daytona_source(tmp_path):
    manager = _new_test_manager()
    provider = _FakeDaytonaProvider()
    manager.provider_capability = SimpleNamespace(runtime_kind="daytona_pty")
    manager.provider = provider
    manager.volume = _FakeVolume()
    deleted_sessions: list[tuple[str, str]] = []
    deleted_terminals: list[str] = []
    destroyed_leases: list[str] = []
    deleted_leases: list[str] = []
    repo = _FakeVolumeRepo(HostVolume(tmp_path / "staging").serialize())
    manager._sandbox_volume_repo = lambda: repo

    class _Lease:
        lease_id = "lease-1"
        observed_state = "detached"
        volume_id = "volume-1"

        def get_instance(self):
            return None

        def destroy_instance(self, _provider):
            destroyed_leases.append("lease-1")

    lease = _Lease()
    all_terminals = [{"terminal_id": "term-1", "lease_id": "lease-1", "thread_id": "thread-1"}]
    manager._get_thread_lease = lambda _thread_id: lease
    manager._get_lease = lambda _lease_id: lease
    manager.terminal_store = SimpleNamespace(
        list_by_thread=lambda thread_id: [row for row in all_terminals if row["thread_id"] == thread_id],
        delete=lambda terminal_id: (
            deleted_terminals.append(terminal_id),
            all_terminals.__setitem__(slice(None), [row for row in all_terminals if row["terminal_id"] != terminal_id]),
        ),
        list_all=lambda: list(all_terminals),
        db_path=Path("/tmp/fake-sandbox.db"),
    )
    manager.session_manager = SimpleNamespace(
        delete_thread=lambda thread_id, reason="thread_deleted": deleted_sessions.append((thread_id, reason)),
    )
    manager.lease_store = SimpleNamespace(delete=lambda lease_id: deleted_leases.append(lease_id))

    assert manager.destroy_thread_resources("thread-1") is True
    assert destroyed_leases == ["lease-1"]
    assert provider.deleted_volumes == ["leon-volume-lease-1"]
    assert repo.deleted == []
    assert deleted_leases == ["lease-1"]


def test_sync_uploads_skips_local_volume_sync_when_lease_has_no_volume_id():
    manager = _new_test_manager()
    manager.provider_capability = SimpleNamespace(runtime_kind="local")
    manager.volume = _FakeVolume()
    manager._get_active_terminal = lambda _thread_id: SimpleNamespace(terminal_id="term-1", lease_id="lease-1")
    manager._get_lease = lambda _lease_id: SimpleNamespace(volume_id=None)
    manager._get_thread_lease = lambda _thread_id: SimpleNamespace(volume_id=None)
    manager._resolve_volume_entry = lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("volume lookup should not happen"))
    manager.session_manager = SimpleNamespace(
        get=lambda _thread_id, _terminal_id: SimpleNamespace(
            lease=SimpleNamespace(get_instance=lambda: SimpleNamespace(instance_id="instance-1"))
        )
    )

    assert manager.sync_uploads("thread-1") is True
    assert manager.volume.upload_calls == []


def test_non_daytona_runtime_rejects_legacy_volume_id_during_mount_setup(tmp_path):
    manager = _new_test_manager()
    manager.provider_capability = SimpleNamespace(runtime_kind="agentbay")
    manager.volume = _FakeVolume()
    manager._get_active_terminal = lambda _thread_id: SimpleNamespace(lease_id="lease-1")
    manager._resolve_sync_source_path = lambda _thread_id: Path(tmp_path) / "channel-root"
    manager._get_lease = lambda _lease_id: SimpleNamespace(volume_id="legacy-volume-1")

    with pytest.raises(ValueError, match="legacy volume_id is not allowed"):
        manager._setup_mounts("thread-1")


def test_sync_paths_use_workspace_file_channel_root_instead_of_volume_source(monkeypatch):
    manager = _new_test_manager()
    manager.provider_capability = SimpleNamespace(runtime_kind="agentbay")
    manager.volume = _FakeVolume()
    manager._get_thread_lease = lambda _thread_id: SimpleNamespace(volume_id="volume-1")
    manager.resolve_volume_source = lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("volume source should stay unused"))

    class _ThreadRepo:
        def get_by_id(self, _thread_id: str):
            return {"current_workspace_id": "ws-1"}

        def close(self) -> None:
            return None

    monkeypatch.setattr(
        sandbox_manager_module,
        "build_storage_container",
        lambda: SimpleNamespace(thread_repo=lambda: _ThreadRepo()),
    )

    manager._sync_to_sandbox("thread-1", "instance-1")
    manager._sync_from_sandbox("thread-1", "instance-1")

    expected_root = user_home_path("file_channels", "ws-1").expanduser().resolve()
    assert manager.volume.upload_calls == [("thread-1", "instance-1", expected_root, "/workspace")]
    assert manager.volume.download_calls == [("thread-1", "instance-1", expected_root, "/workspace")]


def test_get_sandbox_local_provider_does_not_require_volume_bootstrap(tmp_path, monkeypatch):
    manager = SandboxManager(
        provider=LocalSessionProvider(default_cwd=str(tmp_path)),
        db_path=tmp_path / "sandbox.db",
    )

    capability = manager.get_sandbox("thread-local")

    assert capability.command.runtime_owns_cwd is True
    session = manager.session_manager.get("thread-local")
    assert session is not None
    assert session.lease.provider_name == "local"


def test_get_sandbox_auto_resumes_paused_lease_when_reconstructing_session():
    manager = _new_test_manager()
    manager.provider = SimpleNamespace(name="local")
    manager.provider_capability = SimpleNamespace(runtime_kind="local", eager_instance_binding=False)
    manager.volume = _FakeVolume()
    terminal = SimpleNamespace(
        terminal_id="term-1",
        lease_id="lease-1",
        get_state=lambda: SimpleNamespace(cwd="/tmp", env_delta={}, state_version=0),
        update_state=lambda _state: None,
    )
    lease = SimpleNamespace(
        provider_name="local",
        observed_state="paused",
        bind_mounts=None,
        recipe=None,
        get_instance=lambda: SimpleNamespace(instance_id="instance-1"),
    )
    manager._get_active_terminal = lambda _thread_id: terminal
    manager._get_lease = lambda _lease_id: lease
    manager._assert_lease_provider = lambda _lease, _thread_id: None
    manager._ensure_bound_instance = lambda _lease: None
    resume_calls: list[tuple[str, str]] = []
    manager.resume_session = lambda thread_id, source="user_resume": resume_calls.append((thread_id, source)) or True
    manager.session_manager = SimpleNamespace(
        get=lambda _thread_id, _terminal_id: None,
        create=lambda **_kwargs: SimpleNamespace(session_id="sess-1", terminal=terminal, lease=lease),
    )

    manager.get_sandbox("thread-1")

    assert resume_calls == [("thread-1", "auto_resume")]


def test_get_sandbox_auto_resumes_live_session_when_lease_state_is_paused():
    manager = _new_test_manager()
    terminal = SimpleNamespace(
        terminal_id="term-1",
        lease_id="lease-1",
        get_state=lambda: SimpleNamespace(cwd="/tmp", env_delta={}, state_version=0),
    )
    paused_lease = SimpleNamespace(
        lease_id="lease-1",
        provider_name="local",
        observed_state="paused",
        bind_mounts=None,
    )
    resumed_lease = SimpleNamespace(
        lease_id="lease-1",
        provider_name="local",
        observed_state="running",
        bind_mounts=None,
    )
    live_session = SimpleNamespace(
        terminal=terminal,
        lease=paused_lease,
        status="active",
    )

    manager.provider = SimpleNamespace(name="local")
    manager.provider_capability = SimpleNamespace(runtime_kind="local", eager_instance_binding=False)
    manager.volume = _FakeVolume()
    manager._assert_lease_provider = lambda _lease, _thread_id: None
    manager._ensure_bound_instance = lambda _lease: None
    resume_calls: list[tuple[str, str]] = []

    def _get_session(_thread_id, _terminal_id):
        if resume_calls:
            return SimpleNamespace(terminal=terminal, lease=resumed_lease, status="active")
        return live_session

    manager._get_active_terminal = lambda _thread_id: terminal
    manager.resume_session = lambda thread_id, source="user_resume": resume_calls.append((thread_id, source)) or True
    manager.session_manager = SimpleNamespace(get=_get_session)

    capability = manager.get_sandbox("thread-1")

    assert resume_calls == [("thread-1", "auto_resume")]
    assert capability._session.lease is resumed_lease


def test_get_sandbox_routes_bind_mounts_to_provider_thread_state():
    manager = _new_test_manager()
    bind_mount_calls: list[tuple[str, list[dict[str, str]]]] = []
    terminal = SimpleNamespace(
        terminal_id="term-1",
        lease_id="lease-1",
        get_state=lambda: SimpleNamespace(cwd="/tmp", env_delta={}, state_version=0),
    )
    lease = SimpleNamespace(
        lease_id="lease-1",
        provider_name="local",
        observed_state="running",
        get_instance=lambda: SimpleNamespace(instance_id="instance-1"),
    )
    session = SimpleNamespace(terminal=terminal, lease=lease, status="active")

    manager.provider = SimpleNamespace(
        name="local",
        set_thread_bind_mounts=lambda thread_id, mounts: bind_mount_calls.append((thread_id, mounts)),
    )
    manager.provider_capability = SimpleNamespace(runtime_kind="local", eager_instance_binding=False)
    manager._get_active_terminal = lambda _thread_id: terminal
    manager._assert_lease_provider = lambda _lease, _thread_id: None
    manager._ensure_bound_instance = lambda _lease: None
    manager.session_manager = SimpleNamespace(get=lambda _thread_id, _terminal_id: session)

    mounts = [{"source": "/tmp/a", "target": "/workspace/a"}]
    capability = manager.get_sandbox("thread-1", bind_mounts=mounts)

    assert bind_mount_calls == [("thread-1", mounts)]
    assert capability._session is session


def test_get_sandbox_remote_bootstrap_syncs_with_path_source():
    manager = _new_test_manager()
    terminal = SimpleNamespace(
        terminal_id="term-1",
        lease_id="lease-1",
        get_state=lambda: SimpleNamespace(cwd="/tmp", env_delta={}, state_version=0),
        update_state=lambda _state: None,
    )
    lease = SimpleNamespace(
        lease_id="lease-1",
        provider_name="agentbay",
        observed_state="running",
        recipe=None,
        get_instance=lambda: SimpleNamespace(instance_id="instance-1"),
    )
    sync_calls: list[tuple[str, str, Path | None]] = []
    expected_path = Path("/tmp/workspace-files")

    manager.provider = SimpleNamespace(name="agentbay")
    manager.provider_capability = SimpleNamespace(runtime_kind="agentbay", eager_instance_binding=False)
    manager._get_active_terminal = lambda _thread_id: terminal
    manager._get_lease = lambda _lease_id: lease
    manager._assert_lease_provider = lambda _lease, _thread_id: None
    manager._ensure_bound_instance = lambda _lease: None
    manager._setup_mounts = lambda _thread_id: {"source_path": expected_path, "remote_path": "/workspace"}
    manager._sync_to_sandbox = lambda thread_id, instance_id, source=None, files=None: sync_calls.append((thread_id, instance_id, source))
    manager._fire_session_ready = lambda *_args, **_kwargs: None
    manager.session_manager = SimpleNamespace(
        get=lambda _thread_id, _terminal_id: None,
        create=lambda **_kwargs: SimpleNamespace(terminal=terminal, lease=lease, status="active"),
    )

    manager.get_sandbox("thread-1")

    assert sync_calls == [("thread-1", "instance-1", expected_path)]


def test_resume_session_rebinds_live_session_lease_after_resume():
    manager = _new_test_manager()
    terminal = SimpleNamespace(terminal_id="term-1", lease_id="lease-1")
    resumed_lease = SimpleNamespace(
        lease_id="lease-1",
        observed_state="running",
        get_instance=lambda: SimpleNamespace(instance_id="instance-1"),
        resume_instance=lambda _provider, source="user_resume": True,
    )
    stale_lease = SimpleNamespace(lease_id="lease-1", observed_state="paused")
    runtime = SimpleNamespace(lease=stale_lease)
    live_session = SimpleNamespace(
        session_id="sess-1",
        terminal=terminal,
        lease=stale_lease,
        runtime=runtime,
        status="paused",
    )
    manager.provider = SimpleNamespace(name="local")
    manager._get_thread_terminals = lambda _thread_id: [terminal]
    manager._get_thread_lease = lambda _thread_id: resumed_lease
    manager._sync_to_sandbox = lambda *_args, **_kwargs: None
    manager._ensure_chat_session = lambda _thread_id: None
    manager.session_manager = SimpleNamespace(
        get=lambda _thread_id, _terminal_id: live_session,
        resume=lambda _session_id: setattr(live_session, "status", "active"),
    )

    ok = manager.resume_session("thread-1", source="auto_resume")

    assert ok is True
    assert live_session.lease is resumed_lease
    assert runtime.lease is resumed_lease


def test_upgrade_to_daytona_volume_uses_lease_id_for_provider_backend_ref(monkeypatch, tmp_path):
    manager = _new_test_manager()
    manager.provider = _FakeDaytonaProvider()
    update_repo = _FakeUpdateRepo()
    manager._sandbox_volume_repo = lambda: update_repo

    monkeypatch.setenv("LEON_STORAGE_STRATEGY", "supabase")

    volume_name = manager._upgrade_to_daytona_volume(
        "thread-supabase",
        "lease-1",
        "/workspace",
    )

    assert manager.provider.calls == [("lease-1", "/workspace")]
    assert volume_name == "leon-volume-lease-1"
    assert update_repo.closed is False
    assert update_repo.updated == []


def test_upgrade_to_daytona_volume_waits_when_reusing_existing_daytona_volume(monkeypatch, tmp_path):
    manager = _new_test_manager()
    provider = _FakeDaytonaProvider()
    update_repo = _FakeUpdateRepo()
    manager.provider = provider
    manager._sandbox_volume_repo = lambda: update_repo

    def _already_exists(volume_id: str, mount_path: str) -> str:
        provider.calls.append((volume_id, mount_path))
        raise RuntimeError("volume already exists")

    provider.create_managed_volume = _already_exists

    volume_name = manager._upgrade_to_daytona_volume(
        "thread-supabase",
        "lease-1",
        "/workspace",
    )

    assert volume_name == "leon-volume-lease-1"
    assert provider.ready_waits == ["leon-volume-lease-1"]


def test_make_sandbox_monitor_repo_returns_supabase(monkeypatch):
    from storage import runtime as storage_runtime

    class _FakeSupabaseClient:
        def table(self, _name: str):
            return object()

    monkeypatch.setenv("LEON_STORAGE_STRATEGY", "supabase")
    monkeypatch.setattr(
        "backend.web.core.supabase_factory.create_supabase_client",
        lambda: _FakeSupabaseClient(),
    )

    repo = storage_runtime.build_sandbox_monitor_repo()
    try:
        assert repo.__class__.__name__ == "SupabaseSandboxMonitorRepo"
    finally:
        repo.close()


def test_resolve_existing_sandbox_lease_prefers_provider_env_binding() -> None:
    lease_repo = SimpleNamespace(
        find_by_instance=lambda **kwargs: {
            "lease_id": "lease-live",
            "provider_name": kwargs["provider_name"],
            "current_instance_id": kwargs["instance_id"],
        },
        close=lambda: None,
    )

    lease = sandbox_manager_module.resolve_existing_sandbox_lease(
        {
            "provider_name": "daytona",
            "provider_env_id": "sandbox-env-1",
            "config": {"legacy_lease_id": "lease-legacy"},
        },
        resolve_lease=lambda _lease_id: (_ for _ in ()).throw(AssertionError("legacy fallback should stay unused")),
        lease_repo=lease_repo,
    )

    assert lease == {
        "lease_id": "lease-live",
        "provider_name": "daytona",
        "current_instance_id": "sandbox-env-1",
    }


def test_resolve_existing_sandbox_lease_falls_back_to_legacy_lease_id_when_instance_lookup_misses() -> None:
    lease_repo = SimpleNamespace(
        find_by_instance=lambda **_kwargs: None,
        close=lambda: None,
    )
    seen_lease_ids: list[str] = []

    lease = sandbox_manager_module.resolve_existing_sandbox_lease(
        {
            "provider_name": "daytona",
            "provider_env_id": "sandbox-env-1",
            "config": {"legacy_lease_id": "lease-legacy"},
        },
        resolve_lease=lambda lease_id: seen_lease_ids.append(lease_id) or {"lease_id": lease_id},
        lease_repo=lease_repo,
    )

    assert seen_lease_ids == ["lease-legacy"]
    assert lease == {"lease_id": "lease-legacy"}
