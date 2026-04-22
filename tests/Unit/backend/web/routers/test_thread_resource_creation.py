from backend.web.routers import threads as threads_router
from storage import container_cache

LOWER_RUNTIME_KEY = "lease_" + "id"


class _Container:
    pass


class _LeaseRepo:
    def __init__(self) -> None:
        self.created: list[dict[str, str]] = []
        self.closed = False

    def create(self, lower_runtime_id: str, provider_name: str, **kwargs) -> dict[str, str]:
        self.created.append({LOWER_RUNTIME_KEY: lower_runtime_id, "provider_name": provider_name, **kwargs})
        return {LOWER_RUNTIME_KEY: lower_runtime_id, "sandbox_id": "sandbox-from-lease-create"}

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


def test_create_thread_sandbox_resources_uses_runtime_factories_without_db_path(monkeypatch, tmp_path):
    lease_repo = _LeaseRepo()
    terminal_repo = _TerminalRepo()
    workspace_repo = object()
    materialize_calls: list[dict[str, object]] = []

    monkeypatch.setattr(container_cache, "get_storage_container", lambda: _Container())
    monkeypatch.setattr("storage.runtime.build_sandbox_runtime_repo", lambda: lease_repo)
    monkeypatch.setattr("sandbox.control_plane_repos.make_terminal_repo", lambda: terminal_repo)
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
        owner_user_id="owner-1",
    )

    assert workspace_id == "workspace-1"
    assert len(lease_repo.created) == 1
    assert lease_repo.created[0]["provider_name"] == "local"
    assert "volume_id" not in lease_repo.created[0]
    assert len(terminal_repo.created) == 1
    assert terminal_repo.created[0]["thread_id"] == "thread-1"
    assert terminal_repo.created[0][LOWER_RUNTIME_KEY] == lease_repo.created[0][LOWER_RUNTIME_KEY]
    assert terminal_repo.created[0]["initial_cwd"] == "/tmp/workspace"
    assert materialize_calls[0]["sandbox_id"] == "sandbox-from-lease-create"
    assert lease_repo.closed
    assert terminal_repo.closed


def test_create_thread_sandbox_resources_returns_workspace_id(monkeypatch, tmp_path):
    lease_repo = _LeaseRepo()
    terminal_repo = _TerminalRepo()
    workspace_repo = object()

    monkeypatch.setattr(container_cache, "get_storage_container", lambda: _Container())
    monkeypatch.setattr("storage.runtime.build_sandbox_runtime_repo", lambda: lease_repo)
    monkeypatch.setattr("sandbox.control_plane_repos.make_terminal_repo", lambda: terminal_repo)
    monkeypatch.setattr(threads_router, "_materialize_workspace_for_sandbox", lambda *args, **kwargs: "workspace-new")

    workspace_id = threads_router._create_thread_sandbox_resources(
        "thread-1",
        "local",
        {"id": "local:default", "provider_name": "local", "provider_type": "local"},
        cwd="/tmp/workspace",
        workspace_repo=workspace_repo,
        owner_user_id="owner-1",
    )

    assert workspace_id == "workspace-new"
    assert "volume_id" not in lease_repo.created[0]
