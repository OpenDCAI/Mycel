from __future__ import annotations

from types import SimpleNamespace

import pytest

from sandbox import control_plane_repos
from sandbox import manager as sandbox_manager
from sandbox.manager import SandboxManager
from storage.providers.sqlite.chat_session_repo import SQLiteChatSessionRepo
from storage.providers.sqlite.sandbox_runtime_repo import SQLiteSandboxRuntimeRepo
from storage.providers.sqlite.terminal_repo import SQLiteTerminalRepo


class _Provider:
    def get_capability(self):
        return SimpleNamespace(runtime_kind="local")


class _TerminalRepo:
    def __init__(self) -> None:
        self.closed = False
        self.created: list[dict] = []

    def list_by_thread(self, thread_id: str):
        assert thread_id == "thread-1"
        return [{"sandbox_runtime_id": "runtime-1"}]

    def get_active(self, thread_id: str):
        assert thread_id == "thread-1"
        return None

    def create(self, **kwargs):
        self.created.append(kwargs)
        return kwargs

    def close(self) -> None:
        self.closed = True


class _SandboxRuntimeRepo:
    def __init__(self) -> None:
        self.closed = False

    def get(self, sandbox_runtime_id: str):
        assert sandbox_runtime_id == "runtime-1"
        return {"sandbox_runtime_id": "runtime-1", "provider_name": "local"}

    def close(self) -> None:
        self.closed = True


@pytest.mark.parametrize(
    "factory_name",
    [
        "make_terminal_repo",
        "make_chat_session_repo",
    ],
)
def test_sqlite_control_plane_repo_factories_require_explicit_sandbox_db_path(factory_name, monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("LEON_SANDBOX_DB_PATH", raising=False)

    factory = getattr(control_plane_repos, factory_name)

    with pytest.raises(RuntimeError, match="LEON_SANDBOX_DB_PATH"):
        factory()

    assert not (tmp_path / ".leon").exists()


def test_sandbox_runtime_repo_factory_uses_runtime_storage_without_local_path(monkeypatch, tmp_path):
    fake_repo = object()

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LEON_STORAGE_STRATEGY", "supabase")
    monkeypatch.delenv("LEON_SANDBOX_DB_PATH", raising=False)
    monkeypatch.setattr(control_plane_repos, "build_sandbox_runtime_repo", lambda: fake_repo)

    assert control_plane_repos.make_sandbox_runtime_repo() is fake_repo
    assert not (tmp_path / ".leon").exists()


@pytest.mark.parametrize(
    ("factory_name", "builder_name"),
    [
        ("make_terminal_repo", "build_terminal_repo"),
        ("make_chat_session_repo", "build_chat_session_repo"),
    ],
)
def test_terminal_session_repo_factories_use_runtime_storage_without_local_path(
    factory_name,
    builder_name,
    monkeypatch,
    tmp_path,
):
    fake_repo = object()

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LEON_STORAGE_STRATEGY", "supabase")
    monkeypatch.delenv("LEON_SANDBOX_DB_PATH", raising=False)
    monkeypatch.setattr(control_plane_repos, builder_name, lambda: fake_repo, raising=False)

    assert getattr(control_plane_repos, factory_name)() is fake_repo
    assert not (tmp_path / ".leon").exists()


def test_sandbox_manager_requires_explicit_control_plane_db_path(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("LEON_SANDBOX_DB_PATH", raising=False)
    monkeypatch.delenv("LEON_STORAGE_STRATEGY", raising=False)
    monkeypatch.delenv("LEON_SUPABASE_CLIENT_FACTORY", raising=False)

    with pytest.raises(RuntimeError, match="LEON_SANDBOX_DB_PATH"):
        SandboxManager(provider=_Provider())

    assert not (tmp_path / ".leon").exists()


def test_sandbox_manager_uses_runtime_storage_control_plane_without_local_path(monkeypatch, tmp_path):
    fake_terminal_repo = SimpleNamespace(close=lambda: None)
    fake_runtime_repo = SimpleNamespace(close=lambda: None)
    fake_chat_repo = SimpleNamespace(close=lambda: None)

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LEON_STORAGE_STRATEGY", "supabase")
    monkeypatch.delenv("LEON_SANDBOX_DB_PATH", raising=False)
    monkeypatch.setattr("sandbox.manager.make_terminal_repo", lambda db_path=None: fake_terminal_repo)
    monkeypatch.setattr("sandbox.manager.make_sandbox_runtime_repo", lambda db_path=None: fake_runtime_repo)
    monkeypatch.setattr("sandbox.manager.make_chat_session_repo", lambda db_path=None: fake_chat_repo)
    monkeypatch.setattr("sandbox.volume.SandboxVolume", lambda **_kwargs: object())

    manager = SandboxManager(provider=_Provider())

    assert manager.db_path is None
    assert manager.terminal_store is fake_terminal_repo
    assert manager.sandbox_runtime_store is fake_runtime_repo
    assert manager.session_manager._repo is fake_chat_repo
    assert not (tmp_path / ".leon").exists()


def test_manager_helper_functions_use_runtime_storage_without_local_path(monkeypatch, tmp_path):
    terminal_repo = _TerminalRepo()
    runtime_repo = _SandboxRuntimeRepo()

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LEON_STORAGE_STRATEGY", "supabase")
    monkeypatch.delenv("LEON_SANDBOX_DB_PATH", raising=False)
    monkeypatch.setattr(
        sandbox_manager,
        "resolve_sandbox_db_path",
        lambda _db_path=None: (_ for _ in ()).throw(AssertionError("manager helpers must use repo factories")),
    )
    monkeypatch.setattr(sandbox_manager, "make_terminal_repo", lambda db_path=None: terminal_repo)
    monkeypatch.setattr(sandbox_manager, "make_sandbox_runtime_repo", lambda db_path=None: runtime_repo)
    monkeypatch.setattr(
        sandbox_manager,
        "_build_provider_from_name",
        lambda name: SimpleNamespace(default_cwd="/workspace") if name == "local" else None,
    )

    assert sandbox_manager.lookup_sandbox_for_thread("thread-1") == "local"
    assert sandbox_manager.resolve_existing_sandbox_runtime_cwd("runtime-1") == "/workspace"
    assert sandbox_manager.bind_thread_to_existing_sandbox_runtime("thread-1", "runtime-1") == "/workspace"
    assert len(terminal_repo.created) == 1
    assert terminal_repo.created[0]["terminal_id"].startswith("term-")
    assert terminal_repo.created[0]["thread_id"] == "thread-1"
    assert terminal_repo.created[0]["sandbox_runtime_id"] == "runtime-1"
    assert terminal_repo.created[0]["initial_cwd"] == "/workspace"
    assert not (tmp_path / ".leon").exists()


@pytest.mark.parametrize(
    "repo_cls",
    [
        SQLiteTerminalRepo,
        SQLiteChatSessionRepo,
        SQLiteSandboxRuntimeRepo,
    ],
)
def test_sqlite_sandbox_repos_require_explicit_db_path(repo_cls, monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("LEON_SANDBOX_DB_PATH", raising=False)

    with pytest.raises(RuntimeError, match="LEON_SANDBOX_DB_PATH"):
        repo_cls()

    assert not (tmp_path / ".leon").exists()


def test_explicit_sandbox_db_path_is_not_strategy_command_registry(monkeypatch, tmp_path):
    from sandbox.runtime import _uses_strategy_command_registry

    db_path = tmp_path / "sandbox.db"
    monkeypatch.setenv("LEON_STORAGE_STRATEGY", "supabase")
    monkeypatch.setenv("LEON_SANDBOX_DB_PATH", str(db_path))

    assert not _uses_strategy_command_registry(db_path)
