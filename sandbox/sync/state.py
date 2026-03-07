from storage.providers.sqlite.kernel import connect_sqlite_role, SQLiteDBRole
from pathlib import Path
import hashlib


def _calculate_checksum(file_path: Path) -> str:
    """Calculate SHA256 checksum of file."""
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            sha256.update(chunk)
    return sha256.hexdigest()


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

    def track_files_batch(self, thread_id: str, file_records: list[tuple[str, str, int]]):
        """Batch insert/update multiple files in a single transaction.
        file_records: list of (relative_path, checksum, timestamp)
        """
        if not file_records:
            return
        with connect_sqlite_role(SQLiteDBRole.SANDBOX) as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO sync_files VALUES (?, ?, ?, ?)",
                [(thread_id, rp, cs, ts) for rp, cs, ts in file_records]
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

    def get_all_files(self, thread_id: str) -> dict[str, str]:
        """Batch fetch all tracked files for a thread. Returns {relative_path: checksum}."""
        with connect_sqlite_role(SQLiteDBRole.SANDBOX) as conn:
            rows = conn.execute(
                "SELECT relative_path, checksum FROM sync_files WHERE thread_id = ?",
                (thread_id,)
            ).fetchall()
            return {row[0]: row[1] for row in rows}

    def detect_changes(self, thread_id: str, workspace_path: Path) -> list[str]:
        """Detect files that changed since last sync. Uses batch DB query + mtime heuristic."""
        known = self.get_all_files(thread_id)
        changed = []
        for file_path in workspace_path.rglob("*"):
            if not file_path.is_file():
                continue
            relative = str(file_path.relative_to(workspace_path))
            if relative not in known:
                # New file — must upload
                changed.append(relative)
                continue
            # @@@mtime-fast-path - check mtime before expensive checksum
            current_checksum = _calculate_checksum(file_path)
            if current_checksum != known[relative]:
                changed.append(relative)
        return changed
