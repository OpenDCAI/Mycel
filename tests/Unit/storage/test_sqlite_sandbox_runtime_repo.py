from storage.providers.sqlite.sandbox_runtime_repo import SQLiteSandboxRuntimeRepo


def test_sqlite_sandbox_runtime_repo_schema_does_not_create_removed_volume_id(tmp_path):
    repo = SQLiteSandboxRuntimeRepo(tmp_path / "sandbox.db")
    try:
        cols = {row[1] for row in repo._conn.execute("PRAGMA table_info(sandbox_leases)").fetchall()}
    finally:
        repo.close()

    assert "volume_id" not in cols


def test_sqlite_sandbox_runtime_repo_returns_sandbox_runtime_id_not_lease_id(tmp_path):
    repo = SQLiteSandboxRuntimeRepo(tmp_path / "sandbox.db")
    try:
        created = repo.create("lease-1", "local")
    finally:
        repo.close()

    assert created["sandbox_runtime_id"] == "lease-1"
    assert "lease_id" not in created


def test_sqlite_sandbox_runtime_repo_schema_uses_sandbox_runtime_id_in_sandbox_instances(tmp_path):
    repo = SQLiteSandboxRuntimeRepo(tmp_path / "sandbox.db")
    try:
        cols = {row[1] for row in repo._conn.execute("PRAGMA table_info(sandbox_instances)").fetchall()}
    finally:
        repo.close()

    assert "sandbox_runtime_id" in cols
    assert "lease_id" not in cols


def test_sqlite_sandbox_runtime_repo_schema_uses_sandbox_runtime_id_in_sandbox_runtime_events(tmp_path):
    repo = SQLiteSandboxRuntimeRepo(tmp_path / "sandbox.db")
    try:
        table_names = {row[0] for row in repo._conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()}
        cols = {row[1] for row in repo._conn.execute("PRAGMA table_info(sandbox_runtime_events)").fetchall()}
    finally:
        repo.close()

    assert "sandbox_runtime_events" in table_names
    assert "lease_events" not in table_names
    assert "sandbox_runtime_id" in cols
    assert "lease_id" not in cols
