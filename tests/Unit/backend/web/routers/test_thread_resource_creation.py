from backend.web.routers import threads as threads_router
from backend.web.utils import helpers


class _VolumeRepo:
    def __init__(self) -> None:
        self.created: list[tuple[str, str, str, str]] = []
        self.closed = False

    def create(self, volume_id: str, payload: str, name: str, created_at: str) -> None:
        self.created.append((volume_id, payload, name, created_at))

    def close(self) -> None:
        self.closed = True


class _Container:
    def __init__(self, volume_repo: _VolumeRepo) -> None:
        self._volume_repo = volume_repo

    def sandbox_volume_repo(self) -> _VolumeRepo:
        return self._volume_repo


class _LeaseRepo:
    def __init__(self) -> None:
        self.created: list[dict[str, str]] = []
        self.closed = False

    def create(self, lease_id: str, provider_name: str, **kwargs) -> None:
        self.created.append({"lease_id": lease_id, "provider_name": provider_name, **kwargs})

    def close(self) -> None:
        self.closed = True


class _TerminalRepo:
    def __init__(self) -> None:
        self.created: list[dict[str, str]] = []
        self.closed = False

    def create(self, **kwargs) -> None:
        self.created.append(kwargs)

    def close(self) -> None:
        self.closed = True


class _SandboxRepo:
    def __init__(self) -> None:
        self.created: list[object] = []

    def create(self, row) -> None:
        self.created.append(row)


def test_create_thread_sandbox_resources_uses_runtime_factories_without_db_path(monkeypatch, tmp_path):
    volume_repo = _VolumeRepo()
    lease_repo = _LeaseRepo()
    terminal_repo = _TerminalRepo()
    sandbox_repo = _SandboxRepo()
    workspace_repo = object()
    materialize_calls: list[dict[str, object]] = []

    monkeypatch.setattr(helpers, "_get_container", lambda: _Container(volume_repo))
    monkeypatch.setattr("backend.web.core.config.SANDBOX_VOLUME_ROOT", tmp_path / "volumes")
    monkeypatch.setattr("storage.runtime.build_lease_repo", lambda: lease_repo)
    monkeypatch.setattr("storage.runtime.build_terminal_repo", lambda: terminal_repo)
    monkeypatch.setattr(
        threads_router,
        "_materialize_workspace_for_sandbox",
        lambda _workspace_repo, **kwargs: materialize_calls.append(dict(kwargs)) or "workspace-1",
    )

    workspace_id = threads_router._create_thread_sandbox_resources(
        "thread-1",
        "local",
        {"id": "local:default", "provider_name": "local", "provider_type": "local"},
        cwd="/tmp/workspace",
        workspace_repo=workspace_repo,
        sandbox_repo=sandbox_repo,
        owner_user_id="owner-1",
    )

    assert workspace_id == "workspace-1"
    assert len(volume_repo.created) == 1
    assert len(lease_repo.created) == 1
    assert len(sandbox_repo.created) == 1
    assert lease_repo.created[0]["provider_name"] == "local"
    assert len(terminal_repo.created) == 1
    assert terminal_repo.created[0]["thread_id"] == "thread-1"
    assert terminal_repo.created[0]["lease_id"] == lease_repo.created[0]["lease_id"]
    assert terminal_repo.created[0]["initial_cwd"] == "/tmp/workspace"
    assert sandbox_repo.created[0].config["legacy_lease_id"] == lease_repo.created[0]["lease_id"]
    assert materialize_calls[0]["sandbox_id"] == sandbox_repo.created[0].id
    assert volume_repo.closed
    assert lease_repo.closed
    assert terminal_repo.closed


def test_create_thread_sandbox_resources_returns_workspace_id(monkeypatch, tmp_path):
    volume_repo = _VolumeRepo()
    lease_repo = _LeaseRepo()
    terminal_repo = _TerminalRepo()
    sandbox_repo = _SandboxRepo()
    workspace_repo = object()

    monkeypatch.setattr(helpers, "_get_container", lambda: _Container(volume_repo))
    monkeypatch.setattr("backend.web.core.config.SANDBOX_VOLUME_ROOT", tmp_path / "volumes")
    monkeypatch.setattr("storage.runtime.build_lease_repo", lambda: lease_repo)
    monkeypatch.setattr("storage.runtime.build_terminal_repo", lambda: terminal_repo)
    monkeypatch.setattr(threads_router, "_materialize_workspace_for_sandbox", lambda *args, **kwargs: "workspace-new")

    workspace_id = threads_router._create_thread_sandbox_resources(
        "thread-1",
        "local",
        {"id": "local:default", "provider_name": "local", "provider_type": "local"},
        cwd="/tmp/workspace",
        workspace_repo=workspace_repo,
        sandbox_repo=sandbox_repo,
        owner_user_id="owner-1",
    )

    assert workspace_id == "workspace-new"
