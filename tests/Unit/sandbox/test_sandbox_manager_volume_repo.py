import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import sandbox.manager as sandbox_manager_module
from sandbox.manager import SandboxManager
from sandbox.providers.local import LocalSessionProvider
from sandbox.volume_source import DaytonaVolume, HostVolume


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
        self.upload_calls: list[tuple[str, str]] = []
        self.download_calls: list[tuple[str, str]] = []
        self.cleared: list[str] = []

    def resolve_mount_path(self) -> str:
        return "/workspace"

    def mount(self, thread_id: str, source, remote_path: str) -> None:
        self.mount_calls.append((thread_id, remote_path))

    def mount_managed_volume(self, thread_id: str, volume_name: str, remote_path: str) -> None:
        self.mount_calls.append((thread_id, remote_path))

    def sync_upload(self, thread_id: str, session_id: str, source, remote_path: str, files=None) -> None:
        self.upload_calls.append((thread_id, session_id))

    def sync_download(self, thread_id: str, session_id: str, source, remote_path: str) -> None:
        self.download_calls.append((thread_id, session_id))

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
    def __init__(self) -> None:
        self.volume_updates: list[tuple[str, str]] = []

    def set_volume_id(self, lease_id: str, volume_id: str) -> None:
        self.volume_updates.append((lease_id, volume_id))


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


def test_setup_mounts_reads_volume_from_active_storage_repo(tmp_path):
    manager = _new_test_manager()
    manager.provider_capability = SimpleNamespace(runtime_kind="local")
    manager.volume = _FakeVolume()
    manager._get_active_terminal = lambda _thread_id: SimpleNamespace(lease_id="lease-1")
    manager._get_lease = lambda _lease_id: SimpleNamespace(volume_id="volume-1")
    repo = _FakeVolumeRepo(HostVolume(Path(tmp_path) / "vol").serialize())
    manager._sandbox_volume_repo = lambda: repo

    result = manager._setup_mounts("thread-1")

    assert repo.requested_ids == ["volume-1"]
    assert repo.closed is True
    assert isinstance(result["source"], HostVolume)
    assert manager.volume.mount_calls == [("thread-1", "/workspace")]


def test_resolve_volume_source_reads_volume_from_active_storage_repo(tmp_path):
    manager = _new_test_manager()
    manager.provider_capability = SimpleNamespace(runtime_kind="agentbay")
    manager._get_active_terminal = lambda _thread_id: SimpleNamespace(lease_id="lease-1")
    manager._get_lease = lambda _lease_id: SimpleNamespace(volume_id="volume-1")
    repo = _FakeVolumeRepo(HostVolume(Path(tmp_path) / "vol").serialize())
    manager._sandbox_volume_repo = lambda: repo

    source = manager.resolve_volume_source("thread-1")

    assert repo.requested_ids == ["volume-1"]
    assert repo.closed is True
    assert isinstance(source, HostVolume)


def test_setup_mounts_provisions_missing_remote_volume_metadata(monkeypatch, tmp_path):
    manager = _new_test_manager()
    manager.provider_capability = SimpleNamespace(runtime_kind="agentbay")
    manager.volume = _FakeVolume()
    manager._get_active_terminal = lambda _thread_id: SimpleNamespace(lease_id="lease-1")
    lease = SimpleNamespace(lease_id="lease-1", volume_id=None)
    manager._get_lease = lambda _lease_id: lease
    manager.lease_store = _FakeLeaseStore()
    repo = _FakeVolumeRepo(HostVolume(Path(tmp_path) / "vol").serialize())
    manager._sandbox_volume_repo = lambda: repo
    monkeypatch.setenv("LEON_SANDBOX_VOLUME_ROOT", str(tmp_path / "volumes"))

    result = manager._setup_mounts("thread-1")

    assert lease.volume_id is not None
    assert repo.created == [(lease.volume_id, "vol-thread-1")]
    assert manager.lease_store.volume_updates == [("lease-1", lease.volume_id)]
    assert repo.requested_ids == [lease.volume_id]
    assert isinstance(result["source"], HostVolume)


def test_setup_mounts_recreates_missing_remote_volume_row_for_existing_volume_id(monkeypatch, tmp_path):
    class _MissingRowRepo(_FakeVolumeRepo):
        def __init__(self) -> None:
            super().__init__(HostVolume(tmp_path / "vol").serialize())
            self._rows: dict[str, dict[str, str]] = {}

        def get(self, volume_id: str):
            self.requested_ids.append(volume_id)
            return self._rows.get(volume_id)

        def create(self, volume_id: str, source_json: str, name: str | None, created_at: str) -> None:
            super().create(volume_id, source_json, name, created_at)
            self._rows[volume_id] = {"source": source_json}

        def update_source(self, volume_id: str, source_json: str) -> None:
            self._rows[volume_id] = {"source": source_json}
            self._source = json.loads(source_json)

    manager = _new_test_manager()
    manager.provider_capability = SimpleNamespace(runtime_kind="daytona_pty")
    manager.provider = _FakeDaytonaProvider()
    manager.volume = _FakeVolume()
    manager._get_active_terminal = lambda _thread_id: SimpleNamespace(lease_id="lease-1")
    lease = SimpleNamespace(lease_id="lease-1", volume_id="volume-missing")
    manager._get_lease = lambda _lease_id: lease
    manager.lease_store = _FakeLeaseStore()
    repo = _MissingRowRepo()
    manager._sandbox_volume_repo = lambda: repo
    monkeypatch.setenv("LEON_SANDBOX_VOLUME_ROOT", str(tmp_path / "volumes"))

    result = manager._setup_mounts("thread-1")

    assert repo.created == [("volume-missing", "vol-thread-1")]
    assert manager.lease_store.volume_updates == []
    assert repo.requested_ids == ["volume-missing", "volume-missing"]
    assert isinstance(result["source"], DaytonaVolume)
    assert manager.provider.calls == [("volume-missing", "/workspace")]


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


def test_destroy_thread_resources_deletes_daytona_managed_volume_and_volume_row(tmp_path):
    manager = _new_test_manager()
    provider = _FakeDaytonaProvider()
    manager.provider_capability = SimpleNamespace(runtime_kind="daytona_pty")
    manager.provider = provider
    manager.volume = _FakeVolume()
    deleted_sessions: list[tuple[str, str]] = []
    deleted_terminals: list[str] = []
    destroyed_leases: list[str] = []
    deleted_leases: list[str] = []
    repo = _FakeVolumeRepo(DaytonaVolume(tmp_path / "staging", "leon-volume-volume-1").serialize())
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
    assert provider.deleted_volumes == ["leon-volume-volume-1"]
    assert repo.deleted == ["volume-1"]
    assert deleted_leases == ["lease-1"]
    assert all_terminals == []


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


def test_upgrade_to_daytona_volume_uses_volume_id_for_provider_backend_ref(monkeypatch, tmp_path):
    manager = _new_test_manager()
    manager.provider = _FakeDaytonaProvider()
    update_repo = _FakeUpdateRepo()
    manager._sandbox_volume_repo = lambda: update_repo

    monkeypatch.setenv("LEON_STORAGE_STRATEGY", "supabase")

    new_source = manager._upgrade_to_daytona_volume(
        "thread-supabase",
        HostVolume(tmp_path / "staging"),
        "volume-1",
        "/workspace",
    )

    assert manager.provider.calls == [("volume-1", "/workspace")]
    assert isinstance(new_source, DaytonaVolume)
    assert update_repo.closed is True
    assert update_repo.updated


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

    new_source = manager._upgrade_to_daytona_volume(
        "thread-supabase",
        HostVolume(tmp_path / "staging"),
        "volume-1",
        "/workspace",
    )

    assert isinstance(new_source, DaytonaVolume)
    assert provider.ready_waits == ["leon-volume-volume-1"]


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
