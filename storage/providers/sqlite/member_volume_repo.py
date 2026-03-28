"""SQLite repository for member volumes (persistent agent storage)."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from storage.providers.sqlite.connection import create_connection


class SQLiteMemberVolumeRepo:

    def __init__(self, db_path: str | Path, conn: sqlite3.Connection | None = None) -> None:
        self._own_conn = conn is None
        if conn is not None:
            self._conn = conn
        else:
            self._conn = create_connection(db_path)
        self._ensure_tables()

    def close(self) -> None:
        if self._own_conn:
            self._conn.close()

    def upsert(self, member_id: str, provider_type: str,
               volume_id: str, mount_path: str, created_at: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO member_volumes"
            "(member_id, provider_type, volume_id, mount_path, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (member_id, provider_type, volume_id, mount_path, created_at),
        )
        self._conn.commit()

    def get(self, member_id: str, provider_type: str) -> dict[str, Any] | None:
        self._conn.row_factory = sqlite3.Row
        row = self._conn.execute(
            "SELECT member_id, provider_type, volume_id, mount_path, created_at"
            " FROM member_volumes WHERE member_id = ? AND provider_type = ?",
            (member_id, provider_type),
        ).fetchone()
        self._conn.row_factory = None
        return dict(row) if row else None

    def list_by_member(self, member_id: str) -> list[dict[str, Any]]:
        self._conn.row_factory = sqlite3.Row
        rows = self._conn.execute(
            "SELECT member_id, provider_type, volume_id, mount_path, created_at"
            " FROM member_volumes WHERE member_id = ?",
            (member_id,),
        ).fetchall()
        self._conn.row_factory = None
        return [dict(r) for r in rows]

    def delete(self, member_id: str, provider_type: str) -> bool:
        cur = self._conn.execute(
            "DELETE FROM member_volumes WHERE member_id = ? AND provider_type = ?",
            (member_id, provider_type),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def delete_all_for_member(self, member_id: str) -> int:
        cur = self._conn.execute(
            "DELETE FROM member_volumes WHERE member_id = ?",
            (member_id,),
        )
        self._conn.commit()
        return cur.rowcount

    def _ensure_tables(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS member_volumes (
                member_id      TEXT NOT NULL,
                provider_type  TEXT NOT NULL,
                volume_id      TEXT NOT NULL,
                mount_path     TEXT NOT NULL,
                created_at     TEXT NOT NULL,
                PRIMARY KEY (member_id, provider_type)
            )
            """
        )
        self._conn.commit()
