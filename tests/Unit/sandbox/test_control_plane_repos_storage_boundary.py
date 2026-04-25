from __future__ import annotations

import pytest

from sandbox import control_plane_repos


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
