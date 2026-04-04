import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import sandbox.manager as sandbox_manager_module
from sandbox.manager import SandboxManager
from sandbox.providers.local import LocalSessionProvider
from sandbox.volume_source import HostVolume
from sandbox.volume_source import DaytonaVolume


class _FakeVolumeRepo:
    def __init__(self, source: dict[str, str]) -> None:
        self._source = source
        self.closed = False
        self.requested_ids: list[str] = []

    def get(self, volume_id: str):
        self.requested_ids.append(volume_id)
        return {"source": json.dumps(self._source)}

    def close(self) -> None:
        self.closed = True


class _FakeVolume:
    def __init__(self) -> None:
        self.mount_calls: list[tuple[str, str]] = []

    def resolve_mount_path(self) -> str:
        return "/workspace"

    def mount(self, thread_id: str, source, remote_path: str) -> None:
        self.mount_calls.append((thread_id, remote_path))

    def mount_managed_volume(self, thread_id: str, volume_name: str, remote_path: str) -> None:
        self.mount_calls.append((thread_id, remote_path))


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


class _FakeDaytonaProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def create_managed_volume(self, member_id: str, mount_path: str) -> str:
        self.calls.append((member_id, mount_path))
        return f"leon-volume-{member_id}"


def test_setup_mounts_reads_volume_from_active_storage_repo(tmp_path):
    manager = object.__new__(SandboxManager)
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
    manager = object.__new__(SandboxManager)
    manager._get_active_terminal = lambda _thread_id: SimpleNamespace(lease_id="lease-1")
    manager._get_lease = lambda _lease_id: SimpleNamespace(volume_id="volume-1")
    repo = _FakeVolumeRepo(HostVolume(Path(tmp_path) / "vol").serialize())
    manager._sandbox_volume_repo = lambda: repo

    source = manager.resolve_volume_source("thread-1")

    assert repo.requested_ids == ["volume-1"]
    assert repo.closed is True
    assert isinstance(source, HostVolume)


def test_get_sandbox_local_provider_does_not_require_volume_bootstrap(tmp_path):
    manager = SandboxManager(
        provider=LocalSessionProvider(default_cwd=str(tmp_path)),
        db_path=tmp_path / "sandbox.db",
    )

    capability = manager.get_sandbox("thread-local")

    assert capability.command.runtime_owns_cwd is True
    session = manager.session_manager.get("thread-local")
    assert session is not None
    assert session.lease.provider_name == "local"


def test_upgrade_to_daytona_volume_uses_runtime_thread_repo_for_member_lookup(monkeypatch, tmp_path):
    manager = object.__new__(SandboxManager)
    manager.provider = _FakeDaytonaProvider()
    update_repo = _FakeUpdateRepo()
    manager._sandbox_volume_repo = lambda: update_repo

    thread_repo = _FakeThreadRepo({"member_id": "member-supabase"})
    monkeypatch.setattr(
        sandbox_manager_module,
        "build_thread_repo",
        lambda **_kwargs: thread_repo,
        raising=False,
    )
    monkeypatch.setenv("LEON_STORAGE_STRATEGY", "supabase")

    new_source = manager._upgrade_to_daytona_volume(
        "thread-supabase",
        HostVolume(tmp_path / "staging"),
        "volume-1",
        "/workspace",
    )

    assert manager.provider.calls == [("member-supabase", "/workspace")]
    assert thread_repo.closed is True
    assert isinstance(new_source, DaytonaVolume)
    assert update_repo.closed is True
    assert update_repo.updated


@pytest.mark.parametrize(
    ("strategy", "expected_class_name"),
    [
        ("sqlite", "SQLiteSandboxMonitorRepo"),
        ("supabase", "SQLiteSandboxMonitorRepo"),
    ],
)
def test_make_sandbox_monitor_repo_uses_runtime_sandbox_db(monkeypatch, strategy, expected_class_name):
    from backend.web.core import storage_factory

    monkeypatch.setenv("LEON_STORAGE_STRATEGY", strategy)
    storage_factory.make_sandbox_monitor_repo.cache_clear() if hasattr(storage_factory.make_sandbox_monitor_repo, "cache_clear") else None

    repo = storage_factory.make_sandbox_monitor_repo()
    try:
        assert repo.__class__.__name__ == expected_class_name
    finally:
        repo.close()
