import json
from pathlib import Path
from types import SimpleNamespace

from sandbox.manager import SandboxManager
from sandbox.providers.local import LocalSessionProvider
from sandbox.volume_source import HostVolume


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
