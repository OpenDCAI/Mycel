"""SQLite repository for sandbox provider webhook events."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from storage.providers.sqlite.connection import create_connection
from storage.providers.sqlite.kernel import SQLiteDBRole, resolve_role_db_path


class SQLiteProviderEventRepo:
    """Provider event persistence backed by SQLite.

    Thread-safe: all connection access is serialized via a lock.
    """

    def __init__(self, db_path: str | Path | None = None, conn: sqlite3.Connection | None = None) -> None:
        self._own_conn = conn is None
        self._lock = threading.Lock()
        if conn is not None:
            self._conn = conn
        else:
            if db_path is None:
                db_path = resolve_role_db_path(SQLiteDBRole.SANDBOX)
            self._conn = create_connection(db_path)
        self._ensure_table()

    def close(self) -> None:
        if self._own_conn:
            self._conn.close()

    def record(
        self,
        *,
        provider_name: str,
        instance_id: str,
        event_type: str,
        payload: dict[str, Any],
        matched_lease_id: str | None,
    ) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO provider_events (
                    provider_name, instance_id, event_type, payload_json, matched_lease_id, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    provider_name,
                    instance_id,
                    event_type,
                    json.dumps(payload),
                    matched_lease_id,
                    datetime.now().isoformat(),
                ),
            )
            self._conn.commit()

    def list_recent(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            self._conn.row_factory = sqlite3.Row
            rows = self._conn.execute(
                """
                SELECT event_id, provider_name, instance_id, event_type,
                       payload_json, matched_lease_id, created_at
                FROM provider_events
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            self._conn.row_factory = None
        items = [dict(row) for row in rows]
        for item in items:
            payload_raw = item.get("payload_json")
            item["payload"] = json.loads(payload_raw) if payload_raw else {}
        return items

    def _ensure_table(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS provider_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider_name TEXT NOT NULL,
                instance_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                payload_json TEXT,
                matched_lease_id TEXT,
                created_at TIMESTAMP NOT NULL
            )
            """
        )
        self._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_provider_events_created
            ON provider_events(created_at DESC)
            """
        )
        self._conn.commit()
