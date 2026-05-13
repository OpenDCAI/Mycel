from storage.providers.sqlite.sandbox_runtime_repo import SQLiteSandboxRuntimeRepo


def test_sqlite_sandbox_runtime_repo_returns_sandbox_runtime_id(tmp_path):
    repo = SQLiteSandboxRuntimeRepo(tmp_path / "sandbox.db")
    try:
        created = repo.create("runtime-1", "local")
    finally:
        repo.close()

    assert created["sandbox_runtime_id"] == "runtime-1"


def test_sqlite_sandbox_runtime_repo_schema_uses_sandbox_runtime_id_in_sandbox_instances(tmp_path):
    repo = SQLiteSandboxRuntimeRepo(tmp_path / "sandbox.db")
    try:
        cols = {row[1] for row in repo._conn.execute("PRAGMA table_info(sandbox_instances)").fetchall()}
    finally:
        repo.close()

    assert "sandbox_runtime_id" in cols


def test_sqlite_sandbox_runtime_repo_schema_uses_sandbox_runtime_id_in_sandbox_runtime_events(tmp_path):
    repo = SQLiteSandboxRuntimeRepo(tmp_path / "sandbox.db")
    try:
        table_names = {row[0] for row in repo._conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()}
        cols = {row[1] for row in repo._conn.execute("PRAGMA table_info(sandbox_runtime_events)").fetchall()}
    finally:
        repo.close()

    assert "sandbox_runtime_events" in table_names
    assert "sandbox_runtime_id" in cols


def test_sqlite_sandbox_runtime_repo_delete_removes_runtime(tmp_path):
    repo = SQLiteSandboxRuntimeRepo(tmp_path / "sandbox.db")
    try:
        repo.create("runtime-1", "local")
        repo.delete("runtime-1")
        assert repo.get("runtime-1") is None
    finally:
        repo.close()
