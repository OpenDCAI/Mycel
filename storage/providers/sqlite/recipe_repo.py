"""SQLite repo for user-scoped recipe overrides and custom recipes."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from storage.providers.sqlite.connection import create_connection
from storage.providers.sqlite.kernel import SQLiteDBRole, resolve_role_db_path


class SQLiteRecipeRepo:
    def __init__(self, db_path: str | Path | None = None, conn: sqlite3.Connection | None = None) -> None:
        self._own_conn = conn is None
        self._lock = threading.Lock()
        if conn is not None:
            self._conn = conn
        else:
            self._conn = create_connection(resolve_role_db_path(SQLiteDBRole.MAIN, db_path))
        self._ensure_table()

    def close(self) -> None:
        if self._own_conn:
            self._conn.close()

    def list_by_owner(self, owner_user_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT owner_user_id, recipe_id, kind, provider_type, data_json, created_at, updated_at
                FROM library_recipes
                WHERE owner_user_id = ?
                ORDER BY created_at ASC, recipe_id ASC
                """,
                (owner_user_id,),
            ).fetchall()
        return [self._hydrate(row) for row in rows]

    def get(self, owner_user_id: str, recipe_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT owner_user_id, recipe_id, kind, provider_type, data_json, created_at, updated_at
                FROM library_recipes
                WHERE owner_user_id = ? AND recipe_id = ?
                """,
                (owner_user_id, recipe_id),
            ).fetchone()
        if row is None:
            return None
        return self._hydrate(row)

    def upsert(
        self,
        *,
        owner_user_id: str,
        recipe_id: str,
        kind: str,
        provider_type: str,
        data: dict[str, Any],
        created_at: int | None = None,
    ) -> dict[str, Any]:
        if kind not in {"custom", "override"}:
            raise ValueError(f"Unsupported recipe row kind: {kind}")
        now = int(time.time() * 1000)
        existing = self.get(owner_user_id, recipe_id)
        created = int(created_at if created_at is not None else existing["created_at"] if existing else now)
        payload = json.dumps(data, ensure_ascii=False)
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO library_recipes (
                    owner_user_id, recipe_id, kind, provider_type, data_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(owner_user_id, recipe_id) DO UPDATE SET
                    kind = excluded.kind,
                    provider_type = excluded.provider_type,
                    data_json = excluded.data_json,
                    updated_at = excluded.updated_at
                """,
                (owner_user_id, recipe_id, kind, provider_type, payload, created, now),
            )
            self._conn.commit()
        row = self.get(owner_user_id, recipe_id)
        if row is None:
            raise RuntimeError("recipe upsert failed")
        return row

    def delete(self, owner_user_id: str, recipe_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM library_recipes WHERE owner_user_id = ? AND recipe_id = ?",
                (owner_user_id, recipe_id),
            )
            self._conn.commit()
        return cur.rowcount > 0

    def _ensure_table(self) -> None:
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS library_recipes (
                    owner_user_id TEXT NOT NULL,
                    recipe_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    provider_type TEXT NOT NULL,
                    data_json TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    PRIMARY KEY (owner_user_id, recipe_id)
                )
                """
            )
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_library_recipes_owner_kind ON library_recipes(owner_user_id, kind)")
            self._conn.commit()

    def _hydrate(self, row: tuple[Any, ...]) -> dict[str, Any]:
        payload = json.loads(str(row[4]))
        if not isinstance(payload, dict):
            raise ValueError("recipe payload must be an object")
        return {
            "owner_user_id": str(row[0]),
            "recipe_id": str(row[1]),
            "kind": str(row[2]),
            "provider_type": str(row[3]),
            "data": payload,
            "created_at": int(row[5]),
            "updated_at": int(row[6]),
        }
