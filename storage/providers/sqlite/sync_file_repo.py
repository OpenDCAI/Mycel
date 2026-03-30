"""SQLite repo for sync_files state."""

from __future__ import annotations

import threading
from pathlib import Path

from storage.providers.sqlite.connection import create_connection
from storage.providers.sqlite.kernel import SQLiteDBRole, resolve_role_db_path


class SQLiteSyncFileRepo:
    def __init__(self) -> None:
        # @@@sync-repo-thread-safe - SyncManager is shared per provider, so sync state reads/writes can hop threads.
        self._lock = threading.Lock()
        self._db_path = resolve_role_db_path(SQLiteDBRole.SANDBOX)
        self._conn = create_connection(self._db_path)
        self._ensure_table()

    def close(self) -> None:
        self._conn.close()

    def _ensure_table(self) -> None:
        with self._lock:
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS sync_files (
                    thread_id TEXT,
                    relative_path TEXT,
                    checksum TEXT,
                    last_synced INTEGER,
                    PRIMARY KEY (thread_id, relative_path)
                )
            """)
            self._conn.commit()

    def track_file(self, thread_id: str, relative_path: str, checksum: str, timestamp: int) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO sync_files VALUES (?, ?, ?, ?)",
                (thread_id, relative_path, checksum, timestamp),
            )
            self._conn.commit()

    def track_files_batch(self, thread_id: str, file_records: list[tuple[str, str, int]]) -> None:
        if not file_records:
            return
        with self._lock:
            self._conn.executemany(
                "INSERT OR REPLACE INTO sync_files VALUES (?, ?, ?, ?)",
                [(thread_id, rp, cs, ts) for rp, cs, ts in file_records],
            )
            self._conn.commit()

    def get_file_info(self, thread_id: str, relative_path: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT checksum, last_synced FROM sync_files WHERE thread_id = ? AND relative_path = ?",
                (thread_id, relative_path),
            ).fetchone()
        if row:
            return {"checksum": row[0], "last_synced": row[1]}
        return None

    def get_all_files(self, thread_id: str) -> dict[str, str]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT relative_path, checksum FROM sync_files WHERE thread_id = ?",
                (thread_id,),
            ).fetchall()
        return {row[0]: row[1] for row in rows}

    def clear_thread(self, thread_id: str) -> int:
        with self._lock:
            cur = self._conn.execute("DELETE FROM sync_files WHERE thread_id = ?", (thread_id,))
            self._conn.commit()
            return cur.rowcount
