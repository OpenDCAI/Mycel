from storage.providers.sqlite.sandbox_runtime_repo import SQLiteSandboxRuntimeRepo


def test_sqlite_lease_repo_schema_does_not_create_removed_volume_id(tmp_path):
    repo = SQLiteSandboxRuntimeRepo(tmp_path / "sandbox.db")
    try:
        cols = {row[1] for row in repo._conn.execute("PRAGMA table_info(sandbox_leases)").fetchall()}
    finally:
        repo.close()

    assert "volume_id" not in cols
