"""SQLite repository for abstract terminal persistence."""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from sandbox.terminal import (
    REQUIRED_ABSTRACT_TERMINAL_COLUMNS,
    REQUIRED_TERMINAL_POINTER_COLUMNS,
)
from storage.providers.sqlite.connection import create_connection
from storage.providers.sqlite.kernel import SQLiteDBRole, resolve_role_db_path


class SQLiteTerminalRepo:
    """Abstract terminal CRUD backed by SQLite.

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
            self._conn = create_connection(db_path)
        self._ensure_tables()

    @property
    def db_path(self) -> Path:
        return self._db_path

    def close(self) -> None:
        if self._own_conn:
            self._conn.close()

    # ------------------------------------------------------------------
    # Table setup
    # ------------------------------------------------------------------

    def _ensure_tables(self) -> None:
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS abstract_terminals (
                terminal_id TEXT PRIMARY KEY,
                thread_id TEXT NOT NULL,
                lease_id TEXT NOT NULL,
                cwd TEXT NOT NULL,
                env_delta_json TEXT DEFAULT '{}',
                state_version INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS thread_terminal_pointers (
                thread_id TEXT PRIMARY KEY,
                active_terminal_id TEXT NOT NULL,
                default_terminal_id TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (active_terminal_id) REFERENCES abstract_terminals(terminal_id),
                FOREIGN KEY (default_terminal_id) REFERENCES abstract_terminals(terminal_id)
            )
            """
        )
        self._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_abstract_terminals_thread_created
            ON abstract_terminals(thread_id, created_at DESC)
            """
        )
        self._conn.commit()

        abstract_cols = {row[1] for row in self._conn.execute("PRAGMA table_info(abstract_terminals)").fetchall()}
        pointer_cols = {row[1] for row in self._conn.execute("PRAGMA table_info(thread_terminal_pointers)").fetchall()}

        # @@@no-thread-unique - Multi-terminal model requires thread_id to be non-unique in abstract_terminals.
        idx_rows = self._conn.execute("PRAGMA index_list(abstract_terminals)").fetchall()
        unique_index_names = [str(row[1]) for row in idx_rows if int(row[2]) == 1]
        unique_index_columns: dict[str, set[str]] = {}
        for idx_name in unique_index_names:
            info_rows = self._conn.execute(f"PRAGMA index_info({idx_name})").fetchall()
            unique_index_columns[idx_name] = {str(info_row[2]) for info_row in info_rows}

        missing_abstract = REQUIRED_ABSTRACT_TERMINAL_COLUMNS - abstract_cols
        if missing_abstract:
            raise RuntimeError(
                f"abstract_terminals schema mismatch: missing {sorted(missing_abstract)}. Purge ~/.leon/sandbox.db and retry."
            )

        missing_pointer = REQUIRED_TERMINAL_POINTER_COLUMNS - pointer_cols
        if missing_pointer:
            raise RuntimeError(
                f"thread_terminal_pointers schema mismatch: missing {sorted(missing_pointer)}. Purge ~/.leon/sandbox.db and retry."
            )

        if any(cols == {"thread_id"} for cols in unique_index_columns.values()):
            raise RuntimeError("abstract_terminals still has UNIQUE index from single-terminal schema. Purge ~/.leon/sandbox.db and retry.")

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def _get_pointer_row(self, thread_id: str) -> dict[str, Any] | None:
        with self._lock:
            self._conn.row_factory = sqlite3.Row
            row = self._conn.execute(
                """
                SELECT thread_id, active_terminal_id, default_terminal_id
                FROM thread_terminal_pointers
                WHERE thread_id = ?
                """,
                (thread_id,),
            ).fetchone()
            self._conn.row_factory = None
            return dict(row) if row else None

    def get_active(self, thread_id: str) -> dict[str, Any] | None:
        pointer = self._get_pointer_row(thread_id)
        if pointer is None:
            return None
        row = self.get_by_id(str(pointer["active_terminal_id"]))
        if row is not None:
            return row
        latest = self.list_by_thread(thread_id)
        if not latest:
            return None
        # @@@stale-terminal-pointer-heal - stale pointer rows can survive direct
        # row deletion / pre-fix thread bootstrap. Repair against the newest
        # terminal instead of leaving the thread permanently unreadable.
        self._ensure_thread_pointer(thread_id, str(latest[0]["terminal_id"]))
        return self.get_by_id(str(latest[0]["terminal_id"])) or latest[0]

    def get_default(self, thread_id: str) -> dict[str, Any] | None:
        pointer = self._get_pointer_row(thread_id)
        if pointer is None:
            return None
        row = self.get_by_id(str(pointer["default_terminal_id"]))
        if row is not None:
            return row
        latest = self.list_by_thread(thread_id)
        if not latest:
            return None
        self._ensure_thread_pointer(thread_id, str(latest[0]["terminal_id"]))
        return self.get_by_id(str(latest[0]["terminal_id"])) or latest[0]

    def get_by_id(self, terminal_id: str) -> dict[str, Any] | None:
        with self._lock:
            self._conn.row_factory = sqlite3.Row
            row = self._conn.execute(
                """
                SELECT terminal_id, thread_id, lease_id, cwd, env_delta_json, state_version,
                       created_at, updated_at
                FROM abstract_terminals
                WHERE terminal_id = ?
                """,
                (terminal_id,),
            ).fetchone()
            self._conn.row_factory = None
            return dict(row) if row else None

    def get_latest_by_lease(self, lease_id: str) -> dict[str, Any] | None:
        with self._lock:
            self._conn.row_factory = sqlite3.Row
            row = self._conn.execute(
                """
                SELECT terminal_id, thread_id, lease_id, cwd, env_delta_json, state_version,
                       created_at, updated_at
                FROM abstract_terminals
                WHERE lease_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (lease_id,),
            ).fetchone()
            self._conn.row_factory = None
            return dict(row) if row else None

    def get_timestamps(self, terminal_id: str) -> tuple[str | None, str | None]:
        row = self.get_by_id(terminal_id)
        if row is None:
            return None, None
        return str(row.get("created_at") or "") or None, str(row.get("updated_at") or "") or None

    def list_by_thread(self, thread_id: str) -> list[dict[str, Any]]:
        with self._lock:
            self._conn.row_factory = sqlite3.Row
            rows = self._conn.execute(
                """
                SELECT terminal_id, thread_id, lease_id, cwd, env_delta_json, state_version,
                       created_at, updated_at
                FROM abstract_terminals
                WHERE thread_id = ?
                ORDER BY created_at DESC
                """,
                (thread_id,),
            ).fetchall()
            self._conn.row_factory = None
            return [dict(row) for row in rows]

    def list_all(self) -> list[dict[str, Any]]:
        with self._lock:
            self._conn.row_factory = sqlite3.Row
            rows = self._conn.execute(
                """
                SELECT terminal_id, thread_id, lease_id, cwd, env_delta_json, state_version, created_at, updated_at
                FROM abstract_terminals
                ORDER BY created_at DESC
                """
            ).fetchall()
            self._conn.row_factory = None
            return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def _ensure_thread_pointer(self, thread_id: str, terminal_id: str) -> None:
        now = datetime.now().isoformat()
        with self._lock:
            self._conn.row_factory = sqlite3.Row
            row = self._conn.execute(
                """
                SELECT active_terminal_id, default_terminal_id
                FROM thread_terminal_pointers
                WHERE thread_id = ?
                """,
                (thread_id,),
            ).fetchone()
            if row is not None:
                active_row = self._conn.execute(
                    """
                    SELECT terminal_id
                    FROM abstract_terminals
                    WHERE terminal_id = ? AND thread_id = ?
                    """,
                    (str(row["active_terminal_id"]), thread_id),
                ).fetchone()
                default_row = self._conn.execute(
                    """
                    SELECT terminal_id
                    FROM abstract_terminals
                    WHERE terminal_id = ? AND thread_id = ?
                    """,
                    (str(row["default_terminal_id"]), thread_id),
                ).fetchone()
                if active_row is not None and default_row is not None:
                    self._conn.row_factory = None
                    return
                self._conn.execute(
                    """
                    UPDATE thread_terminal_pointers
                    SET active_terminal_id = ?, default_terminal_id = ?, updated_at = ?
                    WHERE thread_id = ?
                    """,
                    (
                        str(row["active_terminal_id"]) if active_row is not None else terminal_id,
                        str(row["default_terminal_id"]) if default_row is not None else terminal_id,
                        now,
                        thread_id,
                    ),
                )
                self._conn.row_factory = None
                self._conn.commit()
                return
            self._conn.execute(
                """
                INSERT INTO thread_terminal_pointers (thread_id, active_terminal_id, default_terminal_id, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (thread_id, terminal_id, terminal_id, now),
            )
            self._conn.row_factory = None
            self._conn.commit()

    def create(
        self,
        terminal_id: str,
        thread_id: str,
        lease_id: str,
        initial_cwd: str = "/root",
    ) -> dict[str, Any]:
        now = datetime.now().isoformat()
        env_delta_json = "{}"
        state_version = 0

        with self._lock:
            self._conn.execute(
                """
                INSERT INTO abstract_terminals (terminal_id, thread_id, lease_id, cwd, env_delta_json, state_version, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (terminal_id, thread_id, lease_id, initial_cwd, env_delta_json, state_version, now, now),
            )
            self._conn.commit()

        self._ensure_thread_pointer(thread_id, terminal_id)

        return {
            "terminal_id": terminal_id,
            "thread_id": thread_id,
            "lease_id": lease_id,
            "cwd": initial_cwd,
            "env_delta_json": env_delta_json,
            "state_version": state_version,
            "created_at": now,
            "updated_at": now,
        }

    def persist_state(
        self,
        *,
        terminal_id: str,
        cwd: str,
        env_delta_json: str,
        state_version: int,
    ) -> None:
        with self._lock:
            self._conn.execute(
                """
                UPDATE abstract_terminals
                SET cwd = ?, env_delta_json = ?, state_version = ?, updated_at = ?
                WHERE terminal_id = ?
                """,
                (cwd, env_delta_json, state_version, datetime.now().isoformat(), terminal_id),
            )
            self._conn.commit()

    def set_active(self, thread_id: str, terminal_id: str) -> None:
        now = datetime.now().isoformat()
        with self._lock:
            self._conn.row_factory = sqlite3.Row
            row = self._conn.execute(
                """
                SELECT terminal_id, thread_id
                FROM abstract_terminals
                WHERE terminal_id = ?
                """,
                (terminal_id,),
            ).fetchone()
            if row is None:
                raise RuntimeError(f"Terminal {terminal_id} not found")
            if row["thread_id"] != thread_id:
                raise RuntimeError(f"Terminal {terminal_id} belongs to thread {row['thread_id']}, not thread {thread_id}")
            pointer = self._conn.execute(
                "SELECT default_terminal_id FROM thread_terminal_pointers WHERE thread_id = ?",
                (thread_id,),
            ).fetchone()
            if pointer is None:
                self._conn.execute(
                    """
                    INSERT INTO thread_terminal_pointers (thread_id, active_terminal_id, default_terminal_id, updated_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (thread_id, terminal_id, terminal_id, now),
                )
            else:
                self._conn.execute(
                    """
                    UPDATE thread_terminal_pointers
                    SET active_terminal_id = ?, updated_at = ?
                    WHERE thread_id = ?
                    """,
                    (terminal_id, now, thread_id),
                )
            self._conn.row_factory = None
            self._conn.commit()

    def delete_by_thread(self, thread_id: str) -> None:
        for terminal in self.list_by_thread(thread_id):
            self.delete(str(terminal["terminal_id"]))

    def delete(self, terminal_id: str) -> None:
        with self._lock:
            self._conn.row_factory = sqlite3.Row
            terminal = self._conn.execute(
                """
                SELECT terminal_id, thread_id
                FROM abstract_terminals
                WHERE terminal_id = ?
                """,
                (terminal_id,),
            ).fetchone()
            if terminal is None:
                self._conn.row_factory = None
                return
            thread_id = str(terminal["thread_id"])

            tables = {row[0] for row in self._conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            if "terminal_commands" in tables:
                if "terminal_command_chunks" in tables:
                    self._conn.execute(
                        """
                        DELETE FROM terminal_command_chunks
                        WHERE command_id IN (
                            SELECT command_id FROM terminal_commands WHERE terminal_id = ?
                        )
                        """,
                        (terminal_id,),
                    )
                self._conn.execute(
                    "DELETE FROM terminal_commands WHERE terminal_id = ?",
                    (terminal_id,),
                )
            self._conn.execute(
                "DELETE FROM abstract_terminals WHERE terminal_id = ?",
                (terminal_id,),
            )

            pointer = self._conn.execute(
                """
                SELECT active_terminal_id, default_terminal_id
                FROM thread_terminal_pointers
                WHERE thread_id = ?
                """,
                (thread_id,),
            ).fetchone()
            if pointer:
                remaining = self._conn.execute(
                    """
                    SELECT terminal_id
                    FROM abstract_terminals
                    WHERE thread_id = ?
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (thread_id,),
                ).fetchone()
                if remaining is None:
                    self._conn.execute(
                        "DELETE FROM thread_terminal_pointers WHERE thread_id = ?",
                        (thread_id,),
                    )
                else:
                    next_terminal_id = str(remaining["terminal_id"])
                    active_terminal_id = str(pointer["active_terminal_id"])
                    default_terminal_id = str(pointer["default_terminal_id"])
                    self._conn.execute(
                        """
                        UPDATE thread_terminal_pointers
                        SET active_terminal_id = ?, default_terminal_id = ?, updated_at = ?
                        WHERE thread_id = ?
                        """,
                        (
                            next_terminal_id if active_terminal_id == terminal_id else active_terminal_id,
                            next_terminal_id if default_terminal_id == terminal_id else default_terminal_id,
                            datetime.now().isoformat(),
                            thread_id,
                        ),
                    )
            self._conn.row_factory = None
            self._conn.commit()
