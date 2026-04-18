from storage.providers.sqlite.lease_repo import SQLiteLeaseRepo


def test_sqlite_lease_repo_schema_does_not_create_removed_volume_id(tmp_path):
    repo = SQLiteLeaseRepo(tmp_path / "sandbox.db")
    try:
        cols = {row[1] for row in repo._conn.execute("PRAGMA table_info(sandbox_leases)").fetchall()}
    finally:
        repo.close()

    assert "volume_id" not in cols
