from __future__ import annotations

from types import SimpleNamespace

import pytest

from sandbox import control_plane_repos
from sandbox.manager import SandboxManager
from storage.providers.sqlite.chat_session_repo import SQLiteChatSessionRepo
from storage.providers.sqlite.sandbox_runtime_repo import SQLiteSandboxRuntimeRepo
from storage.providers.sqlite.terminal_repo import SQLiteTerminalRepo


class _Provider:
    def get_capability(self):
        return SimpleNamespace(runtime_kind="local")


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


def test_sandbox_manager_requires_explicit_control_plane_db_path(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("LEON_SANDBOX_DB_PATH", raising=False)
    monkeypatch.delenv("LEON_STORAGE_STRATEGY", raising=False)
    monkeypatch.delenv("LEON_SUPABASE_CLIENT_FACTORY", raising=False)

    with pytest.raises(RuntimeError, match="LEON_SANDBOX_DB_PATH"):
        SandboxManager(provider=_Provider())

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
