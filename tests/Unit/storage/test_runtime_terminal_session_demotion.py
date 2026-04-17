from sandbox import control_plane_repos
from storage import runtime
from storage.container import _REPO_REGISTRY, StorageContainer
from storage.providers.sqlite.chat_session_repo import SQLiteChatSessionRepo
from storage.providers.sqlite.terminal_repo import SQLiteTerminalRepo


def test_default_terminal_and_chat_session_builders_use_local_runtime_store(monkeypatch, tmp_path):
    monkeypatch.setenv("LEON_SUPABASE_CLIENT_FACTORY", "tests.missing:factory")
    monkeypatch.setenv("LEON_SANDBOX_DB_PATH", str(tmp_path / "sandbox.db"))

    def reject_supabase_repo(repo_method: str, **_kwargs):
        raise AssertionError(f"{repo_method} should not use Supabase staging persistence by default")

    monkeypatch.setattr(runtime, "_build_storage_repo", reject_supabase_repo)

    terminal_repo = runtime.build_terminal_repo()
    chat_session_repo = runtime.build_chat_session_repo()
    try:
        assert isinstance(terminal_repo, SQLiteTerminalRepo)
        assert isinstance(chat_session_repo, SQLiteChatSessionRepo)
    finally:
        terminal_repo.close()
        chat_session_repo.close()


def test_control_plane_terminal_and_chat_session_repos_do_not_route_through_supabase_defaults(monkeypatch, tmp_path):
    monkeypatch.setenv("LEON_SUPABASE_CLIENT_FACTORY", "tests.missing:factory")
    monkeypatch.setenv("LEON_SANDBOX_DB_PATH", str(tmp_path / "sandbox.db"))

    terminal_repo = control_plane_repos.make_terminal_repo()
    chat_session_repo = control_plane_repos.make_chat_session_repo()
    try:
        assert isinstance(terminal_repo, SQLiteTerminalRepo)
        assert isinstance(chat_session_repo, SQLiteChatSessionRepo)
    finally:
        terminal_repo.close()
        chat_session_repo.close()


def test_storage_container_does_not_register_terminal_session_supabase_defaults():
    assert "terminal_repo" not in _REPO_REGISTRY
    assert "chat_session_repo" not in _REPO_REGISTRY
    assert not hasattr(StorageContainer, "terminal_repo")
    assert not hasattr(StorageContainer, "chat_session_repo")
