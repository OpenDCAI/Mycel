from storage.providers.sqlite.kernel import connect_sqlite_role, SQLiteDBRole

class SyncState:
    def __init__(self):
        self._ensure_tables()

    def _ensure_tables(self):
        with connect_sqlite_role(SQLiteDBRole.SANDBOX) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sync_files (
                    thread_id TEXT,
                    relative_path TEXT,
                    checksum TEXT,
                    last_synced INTEGER,
                    PRIMARY KEY (thread_id, relative_path)
                )
            """)

    def track_file(self, thread_id: str, relative_path: str, checksum: str, timestamp: int):
        with connect_sqlite_role(SQLiteDBRole.SANDBOX) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO sync_files VALUES (?, ?, ?, ?)",
                (thread_id, relative_path, checksum, timestamp)
            )

    def get_file_info(self, thread_id: str, relative_path: str) -> dict | None:
        with connect_sqlite_role(SQLiteDBRole.SANDBOX) as conn:
            row = conn.execute(
                "SELECT checksum, last_synced FROM sync_files WHERE thread_id = ? AND relative_path = ?",
                (thread_id, relative_path)
            ).fetchone()
            if row:
                return {"checksum": row[0], "last_synced": row[1]}
            return None
