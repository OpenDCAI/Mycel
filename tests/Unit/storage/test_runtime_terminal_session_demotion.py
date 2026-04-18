from sandbox import control_plane_repos
from storage import contracts, runtime
from storage.providers.sqlite.chat_session_repo import SQLiteChatSessionRepo
from storage.providers.sqlite.terminal_repo import SQLiteTerminalRepo


def test_storage_runtime_no_longer_exports_terminal_chat_builders():
    terminal_builder = "build_" + "terminal_repo"
    chat_builder = "build_chat_" + "session_repo"

    assert not hasattr(runtime, terminal_builder)
    assert not hasattr(runtime, chat_builder)


def test_storage_contracts_do_not_export_terminal_chat_control_plane_protocols():
    terminal_contract = "Terminal" + "Repo"
    chat_contract = "Chat" + "SessionRepo"

    assert not hasattr(contracts, terminal_contract)
    assert not hasattr(contracts, chat_contract)


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
