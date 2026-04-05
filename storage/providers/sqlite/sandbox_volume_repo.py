"""SQLite repository for sandbox volumes (sandbox.db)."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from storage.providers.sqlite.kernel import SQLiteDBRole, connect_sqlite_role


class SQLiteSandboxVolumeRepo:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self._conn = connect_sqlite_role(
            SQLiteDBRole.SANDBOX,
            db_path=db_path,
            check_same_thread=False,
        )
        self._ensure_tables()

    def close(self) -> None:
        self._conn.close()

    def create(self, volume_id: str, source_json: str, name: str | None, created_at: str) -> None:
        self._conn.execute(
            "INSERT INTO sandbox_volumes(volume_id, source, name, created_at) VALUES (?, ?, ?, ?)",
            (volume_id, source_json, name, created_at),
        )
        self._conn.commit()

    def get(self, volume_id: str) -> dict[str, Any] | None:
        self._conn.row_factory = sqlite3.Row
        row = self._conn.execute(
            "SELECT volume_id, source, name, created_at FROM sandbox_volumes WHERE volume_id = ?",
            (volume_id,),
        ).fetchone()
        self._conn.row_factory = None
        return dict(row) if row else None

    def update_source(self, volume_id: str, source_json: str) -> None:
        self._conn.execute(
            "UPDATE sandbox_volumes SET source = ? WHERE volume_id = ?",
            (source_json, volume_id),
        )
        self._conn.commit()

    def list_all(self) -> list[dict[str, Any]]:
        self._conn.row_factory = sqlite3.Row
        rows = self._conn.execute(
            "SELECT volume_id, source, name, created_at FROM sandbox_volumes ORDER BY created_at DESC"
        ).fetchall()
        self._conn.row_factory = None
        return [dict(r) for r in rows]

    def delete(self, volume_id: str) -> bool:
        cur = self._conn.execute("DELETE FROM sandbox_volumes WHERE volume_id = ?", (volume_id,))
        self._conn.commit()
        return cur.rowcount > 0

    def _ensure_tables(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sandbox_volumes (
                volume_id  TEXT PRIMARY KEY,
                name       TEXT,
                source     TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        self._conn.commit()
