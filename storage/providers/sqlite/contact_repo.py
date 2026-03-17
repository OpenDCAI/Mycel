"""SQLite repository for directional contact relationships."""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

from storage.contracts import ContactRow
from storage.providers.sqlite.connection import create_connection
from storage.providers.sqlite.kernel import SQLiteDBRole, resolve_role_db_path


def _retry_on_locked(fn, max_retries=5, delay=0.2):
    for attempt in range(max_retries):
        try:
            return fn()
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e) and attempt < max_retries - 1:
                time.sleep(delay * (attempt + 1))
                continue
            raise


class SQLiteContactRepo:

    def __init__(self, db_path: str | Path | None = None, conn: sqlite3.Connection | None = None) -> None:
        self._own_conn = conn is None
        self._lock = threading.Lock()
        if conn is not None:
            self._conn = conn
        else:
            if db_path is None:
                db_path = resolve_role_db_path(SQLiteDBRole.CHAT)
            self._conn = create_connection(db_path)
        self._ensure_table()

    def close(self) -> None:
        if self._own_conn:
            self._conn.close()

    def upsert(self, row: ContactRow) -> None:
        def _do():
            with self._lock:
                self._conn.execute(
                    "INSERT INTO contacts (owner_entity_id, target_entity_id, relation, created_at, updated_at)"
                    " VALUES (?, ?, ?, ?, ?)"
                    " ON CONFLICT(owner_entity_id, target_entity_id)"
                    " DO UPDATE SET relation=excluded.relation, updated_at=excluded.updated_at",
                    (row.owner_entity_id, row.target_entity_id, row.relation, row.created_at, row.updated_at),
                )
                self._conn.commit()
        _retry_on_locked(_do)

    def get(self, owner_entity_id: str, target_entity_id: str) -> ContactRow | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT owner_entity_id, target_entity_id, relation, created_at, updated_at"
                " FROM contacts WHERE owner_entity_id = ? AND target_entity_id = ?",
                (owner_entity_id, target_entity_id),
            ).fetchone()
        if not row:
            return None
        return ContactRow(
            owner_entity_id=row[0], target_entity_id=row[1],
            relation=row[2], created_at=row[3], updated_at=row[4],
        )

    def list_for_entity(self, owner_entity_id: str) -> list[ContactRow]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT owner_entity_id, target_entity_id, relation, created_at, updated_at"
                " FROM contacts WHERE owner_entity_id = ? ORDER BY created_at",
                (owner_entity_id,),
            ).fetchall()
        return [
            ContactRow(
                owner_entity_id=r[0], target_entity_id=r[1],
                relation=r[2], created_at=r[3], updated_at=r[4],
            )
            for r in rows
        ]

    def delete(self, owner_entity_id: str, target_entity_id: str) -> None:
        def _do():
            with self._lock:
                self._conn.execute(
                    "DELETE FROM contacts WHERE owner_entity_id = ? AND target_entity_id = ?",
                    (owner_entity_id, target_entity_id),
                )
                self._conn.commit()
        _retry_on_locked(_do)

    def _ensure_table(self) -> None:
        with self._lock:
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS contacts (
                    owner_entity_id   TEXT NOT NULL,
                    target_entity_id  TEXT NOT NULL,
                    relation          TEXT NOT NULL DEFAULT 'normal',
                    created_at        REAL NOT NULL,
                    updated_at        REAL,
                    PRIMARY KEY (owner_entity_id, target_entity_id)
                )
            """)
            self._conn.commit()
