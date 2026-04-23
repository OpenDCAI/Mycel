"""SQLite repository for sandbox runtime persistence."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from sandbox.lifecycle import parse_sandbox_runtime_instance_state
from storage.providers.sqlite.kernel import SQLiteDBRole, connect_sqlite, resolve_role_db_path


class SQLiteSandboxRuntimeRepo:
    """Sandbox runtime persistence backed by SQLite.

    Thread-safe: all connection access is serialized via a lock.
    Returns raw dicts — domain object construction is the consumer's job.
    """

    def __init__(self, db_path: str | Path | None = None, conn: sqlite3.Connection | None = None) -> None:
        self._own_conn = conn is None
        self._lock = threading.Lock()
        if conn is not None:
            self._conn = conn
            self._db_path = Path(db_path) if db_path else Path("")
        else:
            if db_path is None:
                db_path = resolve_role_db_path(SQLiteDBRole.SANDBOX)
            self._db_path = Path(db_path)
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = connect_sqlite(db_path, check_same_thread=False)
        self._ensure_tables()

    @property
    def db_path(self) -> Path:
        return self._db_path

    def close(self) -> None:
        if self._own_conn:
            self._conn.close()

    def _require_sandbox_runtime(
        self,
        row: dict[str, Any] | None,
        *,
        sandbox_runtime_id: str,
        operation: str,
    ) -> dict[str, Any]:
        if row is None:
            raise RuntimeError(f"SQLite sandbox runtime repo failed to load runtime after {operation}: {sandbox_runtime_id}")
        return row

    def _runtime_row_from_db_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return dict(row)

    def get(self, sandbox_runtime_id: str) -> dict[str, Any] | None:
        with self._lock:
            self._conn.row_factory = sqlite3.Row
            row = self._conn.execute(
                """
                SELECT sandbox_runtime_id, provider_name, recipe_id, workspace_key,
                       recipe_json,
                       current_instance_id, instance_created_at,
                       desired_state, observed_state, version,
                       observed_at, last_error, needs_refresh,
                       refresh_hint_at, status,
                       created_at, updated_at
                FROM sandbox_runtimes
                WHERE sandbox_runtime_id = ?
                """,
                (sandbox_runtime_id,),
            ).fetchone()
            self._conn.row_factory = None

            if not row:
                return None

            result = self._runtime_row_from_db_row(row)

            # Attach instance data as _instance key
            if result.get("current_instance_id"):
                self._conn.row_factory = sqlite3.Row
                inst_row = self._conn.execute(
                    """
                SELECT instance_id, sandbox_runtime_id, provider_session_id,
                       status, created_at, last_seen_at
                FROM sandbox_instances
                WHERE instance_id = ?
                    """,
                    (result["current_instance_id"],),
                ).fetchone()
                self._conn.row_factory = None
                if inst_row:
                    instance = dict(inst_row)
                    instance["sandbox_runtime_id"] = str(instance["sandbox_runtime_id"])
                    result["_instance"] = instance
                else:
                    result["_instance"] = None
            else:
                result["_instance"] = None

            return result

    def create(
        self,
        sandbox_runtime_id: str,
        provider_name: str,
        recipe_id: str | None = None,
        recipe_json: str | None = None,
    ) -> dict[str, Any]:
        now = datetime.now().isoformat()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO sandbox_runtimes (
                    sandbox_runtime_id, provider_name, recipe_id, recipe_json, desired_state, observed_state,
                    instance_status, version, observed_at, last_error,
                    needs_refresh, refresh_hint_at, status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sandbox_runtime_id,
                    provider_name,
                    recipe_id,
                    recipe_json,
                    "running",
                    "detached",
                    "detached",
                    0,
                    now,
                    None,
                    0,
                    None,
                    "active",
                    now,
                    now,
                ),
            )
            self._conn.commit()
        return self._require_sandbox_runtime(
            self.get(sandbox_runtime_id),
            sandbox_runtime_id=sandbox_runtime_id,
            operation="create",
        )

    def find_by_instance(self, *, provider_name: str, instance_id: str) -> dict[str, Any] | None:
        with self._lock:
            self._conn.row_factory = sqlite3.Row
            row = self._conn.execute(
                """
                SELECT sandbox_runtime_id
                FROM sandbox_runtimes
                WHERE provider_name = ? AND current_instance_id = ?
                LIMIT 1
                """,
                (provider_name, instance_id),
            ).fetchone()
            self._conn.row_factory = None
        if not row:
            return None
        return self.get(row["sandbox_runtime_id"])

    def adopt_instance(
        self,
        *,
        sandbox_runtime_id: str,
        provider_name: str,
        instance_id: str,
        status: str = "unknown",
    ) -> dict[str, Any]:
        existing = self.get(sandbox_runtime_id)
        if existing is None:
            self.create(sandbox_runtime_id=sandbox_runtime_id, provider_name=provider_name)
            existing = self._require_sandbox_runtime(
                self.get(sandbox_runtime_id),
                sandbox_runtime_id=sandbox_runtime_id,
                operation="adopt_instance bootstrap",
            )
        if existing["provider_name"] != provider_name:
            raise RuntimeError(
                f"Sandbox runtime provider mismatch during adopt: runtime={existing['provider_name']}, requested={provider_name}"
            )

        now = datetime.now().isoformat()
        normalized = parse_sandbox_runtime_instance_state(status).value
        desired = "paused" if normalized == "paused" else "running"

        with self._lock:
            self._conn.execute(
                """
                UPDATE sandbox_runtimes
                SET current_instance_id = ?,
                    instance_created_at = ?,
                    desired_state = ?,
                    observed_state = ?,
                    instance_status = ?,
                    version = version + 1,
                    observed_at = ?,
                    last_error = ?,
                    needs_refresh = ?,
                    refresh_hint_at = ?,
                    status = ?,
                    updated_at = ?
                WHERE sandbox_runtime_id = ?
                """,
                (
                    instance_id,
                    now,
                    desired,
                    normalized,
                    normalized,
                    now,
                    None,
                    1,
                    now,
                    "active",
                    now,
                    sandbox_runtime_id,
                ),
            )
            self._conn.execute(
                """
                INSERT INTO sandbox_instances (
                    instance_id, sandbox_runtime_id, provider_session_id, status, created_at, last_seen_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(instance_id) DO UPDATE SET
                    sandbox_runtime_id = excluded.sandbox_runtime_id,
                    status = excluded.status,
                    last_seen_at = excluded.last_seen_at
                """,
                (instance_id, sandbox_runtime_id, instance_id, normalized, now, now),
            )
            self._conn.execute(
                """
                INSERT INTO sandbox_runtime_events (event_id, sandbox_runtime_id, event_type, source, payload_json, error, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"evt-{uuid.uuid4().hex}",
                    sandbox_runtime_id,
                    "observe.status",
                    "adopt",
                    json.dumps({"status": normalized, "instance_id": instance_id}),
                    None,
                    now,
                ),
            )
            self._conn.commit()

        adopted = self.get(sandbox_runtime_id)
        if adopted is None:
            raise RuntimeError(f"Failed to load adopted sandbox runtime: {sandbox_runtime_id}")
        return adopted

    def observe_status(
        self,
        *,
        sandbox_runtime_id: str,
        status: str,
        observed_at: Any = None,
    ) -> dict[str, Any]:
        existing = self._require_sandbox_runtime(
            self.get(sandbox_runtime_id),
            sandbox_runtime_id=sandbox_runtime_id,
            operation="observe_status",
        )
        now = observed_at.isoformat() if isinstance(observed_at, datetime) else (observed_at or datetime.now().isoformat())
        normalized = parse_sandbox_runtime_instance_state(status).value
        current_instance_id = existing.get("current_instance_id")

        with self._lock:
            self._conn.execute(
                """
                UPDATE sandbox_runtimes
                SET current_instance_id = ?,
                    instance_created_at = ?,
                    observed_state = ?,
                    instance_status = ?,
                    version = ?,
                    observed_at = ?,
                    last_error = ?,
                    needs_refresh = ?,
                    refresh_hint_at = ?,
                    status = ?,
                    updated_at = ?
                WHERE sandbox_runtime_id = ?
                """,
                (
                    None if normalized == "detached" else existing.get("current_instance_id"),
                    None if normalized == "detached" else existing.get("instance_created_at"),
                    normalized,
                    normalized,
                    int(existing.get("version") or 0) + 1,
                    now,
                    None,
                    0,
                    None,
                    "expired" if normalized == "detached" else "active",
                    datetime.now().isoformat(),
                    sandbox_runtime_id,
                ),
            )
            if current_instance_id:
                if normalized == "detached":
                    self._conn.execute(
                        """
                        UPDATE sandbox_instances
                        SET status = ?, last_seen_at = ?
                        WHERE instance_id = ?
                        """,
                        ("stopped", now, current_instance_id),
                    )
                else:
                    self._conn.execute(
                        """
                        UPDATE sandbox_instances
                        SET status = ?, last_seen_at = ?
                        WHERE instance_id = ?
                        """,
                        (normalized, now, current_instance_id),
                    )
            self._conn.commit()
        return self._require_sandbox_runtime(
            self.get(sandbox_runtime_id),
            sandbox_runtime_id=sandbox_runtime_id,
            operation="observe_status",
        )

    def persist_metadata(
        self,
        *,
        sandbox_runtime_id: str,
        recipe_id: str | None,
        recipe_json: str | None,
        desired_state: str,
        observed_state: str,
        version: int,
        observed_at: Any,
        last_error: str | None,
        needs_refresh: bool,
        refresh_hint_at: Any = None,
        status: str,
    ) -> dict[str, Any]:
        observed_at_value = observed_at.isoformat() if isinstance(observed_at, datetime) else observed_at
        refresh_hint_value = refresh_hint_at.isoformat() if isinstance(refresh_hint_at, datetime) else refresh_hint_at
        with self._lock:
            self._conn.execute(
                """
                UPDATE sandbox_runtimes
                SET recipe_id = ?,
                    recipe_json = ?,
                    desired_state = ?,
                    observed_state = ?,
                    instance_status = ?,
                    version = ?,
                    observed_at = ?,
                    last_error = ?,
                    needs_refresh = ?,
                    refresh_hint_at = ?,
                    status = ?,
                    updated_at = ?
                WHERE sandbox_runtime_id = ?
                """,
                (
                    recipe_id,
                    recipe_json,
                    desired_state,
                    observed_state,
                    observed_state,
                    version,
                    observed_at_value,
                    last_error,
                    1 if needs_refresh else 0,
                    refresh_hint_value,
                    status,
                    datetime.now().isoformat(),
                    sandbox_runtime_id,
                ),
            )
            self._conn.commit()
        return self._require_sandbox_runtime(
            self.get(sandbox_runtime_id),
            sandbox_runtime_id=sandbox_runtime_id,
            operation="persist_metadata",
        )

    def mark_needs_refresh(self, sandbox_runtime_id: str, hint_at: datetime | None = None) -> bool:
        hinted_at = (hint_at or datetime.now()).isoformat()
        with self._lock:
            cursor = self._conn.execute(
                """
                UPDATE sandbox_runtimes
                SET needs_refresh = 1,
                    refresh_hint_at = ?,
                    version = version + 1,
                    updated_at = ?
                WHERE sandbox_runtime_id = ?
                """,
                (hinted_at, datetime.now().isoformat(), sandbox_runtime_id),
            )
            self._conn.commit()
            return cursor.rowcount > 0

    def delete(self, sandbox_runtime_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM sandbox_instances WHERE sandbox_runtime_id = ?", (sandbox_runtime_id,))
            self._conn.execute("DELETE FROM sandbox_runtime_events WHERE sandbox_runtime_id = ?", (sandbox_runtime_id,))
            self._conn.execute("DELETE FROM sandbox_runtimes WHERE sandbox_runtime_id = ?", (sandbox_runtime_id,))
            self._conn.commit()

        # Clean up per-runtime locks in SQLiteSandboxRuntimeHandle.
        from sandbox.runtime_handle import SQLiteSandboxRuntimeHandle

        with SQLiteSandboxRuntimeHandle._lock_guard:
            SQLiteSandboxRuntimeHandle._runtime_locks.pop(sandbox_runtime_id, None)

    def list_all(self) -> list[dict[str, Any]]:
        with self._lock:
            self._conn.row_factory = sqlite3.Row
            rows = self._conn.execute(
                """
                SELECT sandbox_runtime_id, provider_name, recipe_id, recipe_json, current_instance_id,
                       desired_state, observed_state, version,
                       created_at, updated_at
                FROM sandbox_runtimes
                ORDER BY created_at DESC
                """,
            ).fetchall()
            self._conn.row_factory = None
            return [self._runtime_row_from_db_row(row) for row in rows]

    def list_by_provider(self, provider_name: str) -> list[dict[str, Any]]:
        with self._lock:
            self._conn.row_factory = sqlite3.Row
            rows = self._conn.execute(
                """
                SELECT sandbox_runtime_id, provider_name, recipe_id, recipe_json, current_instance_id,
                       desired_state, observed_state, version,
                       created_at, updated_at
                FROM sandbox_runtimes
                WHERE provider_name = ?
                ORDER BY created_at DESC
                """,
                (provider_name,),
            ).fetchall()
            self._conn.row_factory = None
            return [self._runtime_row_from_db_row(row) for row in rows]

    def _ensure_tables(self) -> None:
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sandbox_runtimes (
                sandbox_runtime_id TEXT PRIMARY KEY,
                provider_name TEXT NOT NULL,
                recipe_id TEXT,
                recipe_json TEXT,
                workspace_key TEXT,
                current_instance_id TEXT,
                instance_created_at TIMESTAMP,
                desired_state TEXT NOT NULL DEFAULT 'running',
                observed_state TEXT NOT NULL DEFAULT 'detached',
                instance_status TEXT NOT NULL DEFAULT 'detached',
                version INTEGER NOT NULL DEFAULT 0,
                observed_at TIMESTAMP,
                last_error TEXT,
                needs_refresh INTEGER NOT NULL DEFAULT 0,
                refresh_hint_at TIMESTAMP,
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP NOT NULL
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sandbox_instances (
                instance_id TEXT PRIMARY KEY,
                sandbox_runtime_id TEXT NOT NULL,
                provider_session_id TEXT NOT NULL,
                status TEXT DEFAULT 'running',
                created_at TIMESTAMP NOT NULL,
                last_seen_at TIMESTAMP NOT NULL
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sandbox_runtime_events (
                event_id TEXT PRIMARY KEY,
                sandbox_runtime_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                source TEXT NOT NULL,
                payload_json TEXT,
                error TEXT,
                created_at TIMESTAMP NOT NULL
            )
            """
        )
        self._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_sandbox_runtime_events_runtime_created
            ON sandbox_runtime_events(sandbox_runtime_id, created_at DESC)
            """
        )
        self._conn.commit()

        from sandbox.runtime_handle import REQUIRED_EVENT_COLUMNS, REQUIRED_INSTANCE_COLUMNS, REQUIRED_SANDBOX_RUNTIME_COLUMNS

        runtime_cols = {row[1] for row in self._conn.execute("PRAGMA table_info(sandbox_runtimes)").fetchall()}
        instance_cols = {row[1] for row in self._conn.execute("PRAGMA table_info(sandbox_instances)").fetchall()}
        event_cols = {row[1] for row in self._conn.execute("PRAGMA table_info(sandbox_runtime_events)").fetchall()}

        missing_runtime = REQUIRED_SANDBOX_RUNTIME_COLUMNS - runtime_cols
        if missing_runtime:
            raise RuntimeError(f"sandbox_runtimes schema mismatch: missing {sorted(missing_runtime)}. Purge ~/.leon/sandbox.db and retry.")
        missing_instances = REQUIRED_INSTANCE_COLUMNS - instance_cols
        if missing_instances:
            raise RuntimeError(
                f"sandbox_instances schema mismatch: missing {sorted(missing_instances)}. Purge ~/.leon/sandbox.db and retry."
            )
        missing_events = REQUIRED_EVENT_COLUMNS - event_cols
        if missing_events:
            raise RuntimeError(
                f"sandbox_runtime_events schema mismatch: missing {sorted(missing_events)}. Purge ~/.leon/sandbox.db and retry."
            )
