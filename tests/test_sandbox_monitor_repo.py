from storage.providers.sqlite.lease_repo import SQLiteLeaseRepo
from storage.providers.sqlite.sandbox_monitor_repo import SQLiteSandboxMonitorRepo
from storage.providers.sqlite.chat_session_repo import SQLiteChatSessionRepo
from storage.providers.sqlite.terminal_repo import SQLiteTerminalRepo


def test_list_sessions_with_leases_falls_back_to_abstract_terminals(tmp_path):
    db_path = tmp_path / "sandbox.db"

    lease_repo = SQLiteLeaseRepo(db_path=db_path)
    terminal_repo = SQLiteTerminalRepo(db_path=db_path)
    chat_session_repo = SQLiteChatSessionRepo(db_path=db_path)
    monitor_repo = SQLiteSandboxMonitorRepo(db_path=db_path)
    try:
        lease_repo.create(
            lease_id="lease-1",
            provider_name="local",
            recipe_id="local:default",
        )
        terminal_repo.create(
            terminal_id="term-1",
            thread_id="thread-1",
            lease_id="lease-1",
            initial_cwd="/tmp/one",
        )
        terminal_repo.create(
            terminal_id="term-2",
            thread_id="thread-2",
            lease_id="lease-1",
            initial_cwd="/tmp/two",
        )

        rows = monitor_repo.list_sessions_with_leases()
    finally:
        lease_repo.close()
        terminal_repo.close()
        chat_session_repo.close()
        monitor_repo.close()

    threads = {(row["lease_id"], row["thread_id"], row["session_id"]) for row in rows}
    assert ("lease-1", "thread-1", None) in threads
    assert ("lease-1", "thread-2", None) in threads
