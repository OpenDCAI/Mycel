from storage.providers.sqlite.chat_session_repo import SQLiteChatSessionRepo


def test_chat_session_repo_create_returns_sandbox_runtime_id(tmp_path):
    repo = SQLiteChatSessionRepo(tmp_path / "sandbox.db")
    try:
        created = repo.create_session(
            session_id="sess-1",
            thread_id="thread-1",
            terminal_id="term-1",
            sandbox_runtime_id="runtime-1",
        )
    finally:
        repo.close()

    assert created["sandbox_runtime_id"] == "runtime-1"
    assert "lease_id" not in created


def test_chat_session_repo_get_returns_sandbox_runtime_id(tmp_path):
    repo = SQLiteChatSessionRepo(tmp_path / "sandbox.db")
    try:
        repo.create_session(
            session_id="sess-1",
            thread_id="thread-1",
            terminal_id="term-1",
            sandbox_runtime_id="runtime-1",
        )
        row = repo.get_session("thread-1", "term-1")
    finally:
        repo.close()

    assert row is not None
    assert row["sandbox_runtime_id"] == "runtime-1"
    assert "lease_id" not in row


def test_chat_session_repo_schema_uses_sandbox_runtime_id_column(tmp_path):
    repo = SQLiteChatSessionRepo(tmp_path / "sandbox.db")
    try:
        cols = {row[1] for row in repo._conn.execute("PRAGMA table_info(chat_sessions)").fetchall()}
    finally:
        repo.close()

    assert "sandbox_runtime_id" in cols
    assert "lease_id" not in cols
