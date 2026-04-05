"""SQLite repository for directional contact relationships."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from storage.contracts import ContactRow
from storage.providers.sqlite.connection import create_connection
from storage.providers.sqlite.kernel import SQLiteDBRole, resolve_role_db_path
from storage.providers.sqlite.kernel import retry_on_locked as _retry_on_locked


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
                    "INSERT INTO contacts (owner_id, target_id, relation, created_at, updated_at)"
                    " VALUES (?, ?, ?, ?, ?)"
                    " ON CONFLICT(owner_id, target_id)"
                    " DO UPDATE SET relation=excluded.relation, updated_at=excluded.updated_at",
                    (row.owner_id, row.target_id, row.relation, row.created_at, row.updated_at),
                )
                self._conn.commit()

        _retry_on_locked(_do)

    def get(self, owner_id: str, target_id: str) -> ContactRow | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT owner_id, target_id, relation, created_at, updated_at FROM contacts WHERE owner_id = ? AND target_id = ?",
                (owner_id, target_id),
            ).fetchone()
        if not row:
            return None
        return ContactRow(
            owner_id=row[0],
            target_id=row[1],
            relation=row[2],
            created_at=row[3],
            updated_at=row[4],
        )

    def list_for_user(self, owner_id: str) -> list[ContactRow]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT owner_id, target_id, relation, created_at, updated_at FROM contacts WHERE owner_id = ? ORDER BY created_at",
                (owner_id,),
            ).fetchall()
        return [
            ContactRow(
                owner_id=r[0],
                target_id=r[1],
                relation=r[2],
                created_at=r[3],
                updated_at=r[4],
            )
            for r in rows
        ]

    def delete(self, owner_id: str, target_id: str) -> None:
        def _do():
            with self._lock:
                self._conn.execute(
                    "DELETE FROM contacts WHERE owner_id = ? AND target_id = ?",
                    (owner_id, target_id),
                )
                self._conn.commit()

        _retry_on_locked(_do)

    def _ensure_table(self) -> None:
        with self._lock:
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS contacts (
                    owner_id   TEXT NOT NULL,
                    target_id  TEXT NOT NULL,
                    relation          TEXT NOT NULL DEFAULT 'normal',
                    created_at        REAL NOT NULL,
                    updated_at        REAL,
                    PRIMARY KEY (owner_id, target_id)
                )
            """)
            # @@@entity-id-to-user-id-migration — rename columns for existing databases
            try:
                self._conn.execute("ALTER TABLE contacts RENAME COLUMN owner_entity_id TO owner_id")
            except sqlite3.OperationalError:
                pass
            try:
                self._conn.execute("ALTER TABLE contacts RENAME COLUMN target_entity_id TO target_id")
            except sqlite3.OperationalError:
                pass
            self._conn.commit()
