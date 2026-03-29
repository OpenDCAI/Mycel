"""Provider event persistence for webhook/reconcile driven invalidation."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from storage.providers.sqlite.kernel import connect_sqlite

from sandbox.config import DEFAULT_DB_PATH


def _connect(db_path: Path) -> sqlite3.Connection:
    return connect_sqlite(db_path)


class ProviderEventStore:
    def __init__(self, db_path: Path = DEFAULT_DB_PATH):
        self.db_path = db_path
        self._ensure_table()

    def _ensure_table(self) -> None:
        with _connect(self.db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
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
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_provider_events_created
                ON provider_events(created_at DESC)
                """
            )
            conn.commit()

    def record(
        self,
        *,
        provider_name: str,
        instance_id: str,
        event_type: str,
        payload: dict[str, Any],
        matched_lease_id: str | None,
    ) -> None:
        with _connect(self.db_path) as conn:
            conn.execute(
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
            conn.commit()

    def list_recent(self, limit: int = 100) -> list[dict[str, Any]]:
        with _connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT event_id, provider_name, instance_id, event_type, payload_json, matched_lease_id, created_at
                FROM provider_events
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            items = [dict(row) for row in rows]
            for item in items:
                payload_raw = item.get("payload_json")
                item["payload"] = json.loads(payload_raw) if payload_raw else {}
            return items
