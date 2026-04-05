"""SQLite repo for per-user/member new-thread config memory."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from storage.providers.sqlite.connection import create_connection
from storage.providers.sqlite.kernel import SQLiteDBRole, resolve_role_db_path


class SQLiteThreadLaunchPrefRepo:
    """Persist per-user/member last confirmed + successful new-thread config."""

    def __init__(self, db_path: str | Path | None = None, conn: sqlite3.Connection | None = None) -> None:
        self._own_conn = conn is None
        self._lock = threading.Lock()
        if conn is not None:
            self._conn = conn
        else:
            if db_path is None:
                db_path = resolve_role_db_path(SQLiteDBRole.MAIN)
            self._conn = create_connection(db_path)
        self._ensure_table()

    def close(self) -> None:
        if self._own_conn:
            self._conn.close()

    def get(self, owner_user_id: str, member_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT owner_user_id, member_id, last_confirmed_json, last_successful_json,
                       last_confirmed_at, last_successful_at
                FROM thread_launch_prefs
                WHERE owner_user_id = ? AND member_id = ?
                """,
                (owner_user_id, member_id),
            ).fetchone()
        if row is None:
            return None
        return {
            "owner_user_id": row[0],
            "member_id": row[1],
            "last_confirmed": json.loads(row[2]) if row[2] else None,
            "last_successful": json.loads(row[3]) if row[3] else None,
            "last_confirmed_at": row[4],
            "last_successful_at": row[5],
        }

    def save_confirmed(self, owner_user_id: str, member_id: str, config: dict[str, Any]) -> None:
        self._save(owner_user_id, member_id, "last_confirmed_json", "last_confirmed_at", config)

    def save_successful(self, owner_user_id: str, member_id: str, config: dict[str, Any]) -> None:
        self._save(owner_user_id, member_id, "last_successful_json", "last_successful_at", config)

    def _save(
        self,
        owner_user_id: str,
        member_id: str,
        json_col: str,
        ts_col: str,
        config: dict[str, Any],
    ) -> None:
        payload = json.dumps(config, ensure_ascii=False)
        now = time.time()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO thread_launch_prefs (
                    owner_user_id, member_id, last_confirmed_json, last_successful_json,
                    last_confirmed_at, last_successful_at
                ) VALUES (?, ?, NULL, NULL, NULL, NULL)
                ON CONFLICT(owner_user_id, member_id) DO NOTHING
                """,
                (owner_user_id, member_id),
            )
            self._conn.execute(
                f"UPDATE thread_launch_prefs SET {json_col} = ?, {ts_col} = ? WHERE owner_user_id = ? AND member_id = ?",  # noqa: E501
                (payload, now, owner_user_id, member_id),
            )
            self._conn.commit()

    def _ensure_table(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS thread_launch_prefs (
                owner_user_id TEXT NOT NULL,
                member_id TEXT NOT NULL,
                last_confirmed_json TEXT,
                last_successful_json TEXT,
                last_confirmed_at REAL,
                last_successful_at REAL,
                PRIMARY KEY (owner_user_id, member_id)
            )
            """
        )
        self._conn.commit()
