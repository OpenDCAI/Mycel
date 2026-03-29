"""SQLite repository for file channels (sandbox.db)."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from storage.providers.sqlite.kernel import SQLiteDBRole, connect_sqlite_role


class SQLiteFileChannelRepo:

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._conn = connect_sqlite_role(
            SQLiteDBRole.SANDBOX,
            db_path=db_path,
            check_same_thread=False,
        )
        self._ensure_tables()

    def close(self) -> None:
        self._conn.close()

    def create(self, channel_id: str, source_json: str, name: str | None, created_at: str) -> None:
        self._conn.execute(
            "INSERT INTO file_channels(channel_id, source, name, created_at) VALUES (?, ?, ?, ?)",
            (channel_id, source_json, name, created_at),
        )
        self._conn.commit()

    def get(self, channel_id: str) -> dict[str, Any] | None:
        self._conn.row_factory = sqlite3.Row
        row = self._conn.execute(
            "SELECT channel_id, source, name, created_at FROM file_channels WHERE channel_id = ?",
            (channel_id,),
        ).fetchone()
        self._conn.row_factory = None
        return dict(row) if row else None

    def update_source(self, channel_id: str, source_json: str) -> None:
        self._conn.execute(
            "UPDATE file_channels SET source = ? WHERE channel_id = ?",
            (source_json, channel_id),
        )
        self._conn.commit()

    def list_all(self) -> list[dict[str, Any]]:
        self._conn.row_factory = sqlite3.Row
        rows = self._conn.execute(
            "SELECT channel_id, source, name, created_at FROM file_channels ORDER BY created_at DESC"
        ).fetchall()
        self._conn.row_factory = None
        return [dict(r) for r in rows]

    def delete(self, channel_id: str) -> bool:
        cur = self._conn.execute("DELETE FROM file_channels WHERE channel_id = ?", (channel_id,))
        self._conn.commit()
        return cur.rowcount > 0

    def _ensure_tables(self) -> None:
        # @@@migrate-sandbox-volumes - rename old table if it exists
        tables = {r[0] for r in self._conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        if "sandbox_volumes" in tables and "file_channels" not in tables:
            self._conn.execute("ALTER TABLE sandbox_volumes RENAME TO file_channels")
            self._conn.execute("ALTER TABLE file_channels RENAME COLUMN volume_id TO channel_id")
            self._conn.commit()
        else:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS file_channels (
                    channel_id TEXT PRIMARY KEY,
                    name       TEXT,
                    source     TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            self._conn.commit()
