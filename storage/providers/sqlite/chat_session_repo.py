"""SQLite repository for chat session persistence."""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from sandbox.chat_session import REQUIRED_CHAT_SESSION_COLUMNS
from storage.providers.sqlite.kernel import SQLiteDBRole, connect_sqlite, resolve_role_db_path


class SQLiteChatSessionRepo:
    """Chat session CRUD backed by SQLite.

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

    # ------------------------------------------------------------------
    # Table setup
    # ------------------------------------------------------------------

    def _ensure_tables(self) -> None:
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_sessions (
                chat_session_id TEXT PRIMARY KEY,
                thread_id TEXT NOT NULL,
                terminal_id TEXT NOT NULL,
                lease_id TEXT NOT NULL,
                runtime_id TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                idle_ttl_sec INTEGER NOT NULL,
                max_duration_sec INTEGER NOT NULL,
                budget_json TEXT,
                started_at TIMESTAMP NOT NULL,
                last_active_at TIMESTAMP NOT NULL,
                ended_at TIMESTAMP,
                close_reason TEXT,
                FOREIGN KEY (terminal_id) REFERENCES abstract_terminals(terminal_id),
                FOREIGN KEY (lease_id) REFERENCES sandbox_leases(lease_id)
            )
            """
        )
        self._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_chat_sessions_thread_status
            ON chat_sessions(thread_id, status, started_at DESC)
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS terminal_commands (
                command_id TEXT PRIMARY KEY,
                terminal_id TEXT NOT NULL,
                chat_session_id TEXT,
                command_line TEXT NOT NULL,
                cwd TEXT NOT NULL,
                status TEXT NOT NULL,
                stdout TEXT DEFAULT '',
                stderr TEXT DEFAULT '',
                exit_code INTEGER,
                created_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP NOT NULL,
                finished_at TIMESTAMP,
                FOREIGN KEY (terminal_id) REFERENCES abstract_terminals(terminal_id),
                FOREIGN KEY (chat_session_id) REFERENCES chat_sessions(chat_session_id)
            )
            """
        )
        self._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_terminal_commands_terminal_created
            ON terminal_commands(terminal_id, created_at DESC)
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS terminal_command_chunks (
                chunk_id INTEGER PRIMARY KEY AUTOINCREMENT,
                command_id TEXT NOT NULL,
                stream TEXT NOT NULL CHECK (stream IN ('stdout', 'stderr')),
                content TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL,
                FOREIGN KEY (command_id) REFERENCES terminal_commands(command_id)
            )
            """
        )
        self._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_terminal_command_chunks_command_order
            ON terminal_command_chunks(command_id, chunk_id)
            """
        )
        self._conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_chat_sessions_active_thread
            ON chat_sessions(terminal_id)
            WHERE status IN ('active', 'idle', 'paused')
            """
        )
        self._conn.commit()
        cols = {row[1] for row in self._conn.execute("PRAGMA table_info(chat_sessions)").fetchall()}
        idx_rows = self._conn.execute("PRAGMA index_list(chat_sessions)").fetchall()
        unique_indexes = [str(row[1]) for row in idx_rows if int(row[2]) == 1]
        unique_index_columns: dict[str, set[str]] = {}
        for idx_name in unique_indexes:
            info_rows = self._conn.execute(f"PRAGMA index_info({idx_name})").fetchall()
            unique_index_columns[idx_name] = {str(info_row[2]) for info_row in info_rows}

        missing = REQUIRED_CHAT_SESSION_COLUMNS - cols
        if missing:
            raise RuntimeError(f"chat_sessions schema mismatch: missing {sorted(missing)}. Purge ~/.leon/sandbox.db and retry.")
        # @@@single-active-per-terminal - multi-terminal model allows many active sessions per thread, one per terminal.
        if any(cols == {"thread_id"} for cols in unique_index_columns.values()):
            raise RuntimeError("chat_sessions still has UNIQUE index on thread_id from old schema. Purge ~/.leon/sandbox.db and retry.")

    # Alias for protocol compliance
    ensure_tables = _ensure_tables

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def get_session(self, thread_id: str, terminal_id: str | None = None) -> dict[str, Any] | None:
        with self._lock:
            self._conn.row_factory = sqlite3.Row
            if terminal_id is not None:
                row = self._conn.execute(
                    """
                    SELECT chat_session_id AS session_id, thread_id, terminal_id, lease_id,
                           runtime_id, status, idle_ttl_sec, max_duration_sec,
                           budget_json, started_at, last_active_at, ended_at, close_reason
                    FROM chat_sessions
                    WHERE thread_id = ? AND terminal_id = ? AND status IN ('active', 'idle', 'paused')
                    ORDER BY started_at DESC
                    LIMIT 1
                    """,
                    (thread_id, terminal_id),
                ).fetchone()
            else:
                row = self._conn.execute(
                    """
                    SELECT chat_session_id AS session_id, thread_id, terminal_id, lease_id,
                           runtime_id, status, idle_ttl_sec, max_duration_sec,
                           budget_json, started_at, last_active_at, ended_at, close_reason
                    FROM chat_sessions
                    WHERE thread_id = ? AND status IN ('active', 'idle', 'paused')
                    ORDER BY started_at DESC
                    LIMIT 1
                    """,
                    (thread_id,),
                ).fetchone()
            self._conn.row_factory = None
            return dict(row) if row else None

    def get_session_by_id(self, session_id: str) -> dict[str, Any] | None:
        with self._lock:
            self._conn.row_factory = sqlite3.Row
            row = self._conn.execute(
                """
                SELECT chat_session_id AS session_id, thread_id, terminal_id, lease_id,
                       runtime_id, status, idle_ttl_sec, max_duration_sec,
                       budget_json, started_at, last_active_at, ended_at, close_reason
                FROM chat_sessions
                WHERE chat_session_id = ?
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()
            self._conn.row_factory = None
            return dict(row) if row else None

    def load_status(self, session_id: str) -> str | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT status
                FROM chat_sessions
                WHERE chat_session_id = ?
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()
            return str(row[0]) if row else None

    def get_session_policy(self, session_id: str) -> dict[str, Any] | None:
        with self._lock:
            self._conn.row_factory = sqlite3.Row
            row = self._conn.execute(
                """
                SELECT idle_ttl_sec, max_duration_sec
                FROM chat_sessions
                WHERE chat_session_id = ?
                """,
                (session_id,),
            ).fetchone()
            self._conn.row_factory = None
            return dict(row) if row else None

    def list_active(self) -> list[dict[str, Any]]:
        with self._lock:
            self._conn.row_factory = sqlite3.Row
            rows = self._conn.execute(
                """
                SELECT chat_session_id AS session_id, thread_id, terminal_id, lease_id,
                       runtime_id, status, idle_ttl_sec, max_duration_sec,
                       budget_json, started_at, last_active_at,
                       ended_at, close_reason
                FROM chat_sessions
                WHERE status IN ('active', 'idle', 'paused')
                ORDER BY started_at DESC
                """
            ).fetchall()
            self._conn.row_factory = None
            return [dict(row) for row in rows]

    def list_all(self) -> list[dict[str, Any]]:
        with self._lock:
            self._conn.row_factory = sqlite3.Row
            rows = self._conn.execute(
                """
                SELECT chat_session_id AS session_id, thread_id, terminal_id, lease_id,
                       runtime_id, status, budget_json, started_at, last_active_at,
                       ended_at, close_reason
                FROM chat_sessions
                ORDER BY started_at DESC
                """
            ).fetchall()
            self._conn.row_factory = None
            return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def create_session(
        self,
        session_id: str,
        thread_id: str,
        terminal_id: str,
        lease_id: str,
        *,
        runtime_id: str | None = None,
        status: str = "active",
        idle_ttl_sec: int = 600,
        max_duration_sec: int = 86400,
        budget_json: str | None = None,
        started_at: str | None = None,
        last_active_at: str | None = None,
    ) -> dict[str, Any]:
        now_iso = started_at or datetime.now().isoformat()
        last_active = last_active_at or now_iso
        with self._lock:
            # Supersede any existing active sessions for this terminal
            self._conn.execute(
                """
                UPDATE chat_sessions
                SET status = 'closed', ended_at = ?, close_reason = 'superseded'
                WHERE terminal_id = ? AND status IN ('active', 'idle', 'paused')
                """,
                (now_iso, terminal_id),
            )
            self._conn.execute(
                """
                INSERT INTO chat_sessions (
                    chat_session_id, thread_id, terminal_id, lease_id,
                    runtime_id, status, idle_ttl_sec, max_duration_sec,
                    budget_json, started_at, last_active_at, ended_at, close_reason
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    thread_id,
                    terminal_id,
                    lease_id,
                    runtime_id,
                    status,
                    idle_ttl_sec,
                    max_duration_sec,
                    budget_json,
                    now_iso,
                    last_active,
                    None,
                    None,
                ),
            )
            self._conn.commit()
        return {
            "session_id": session_id,
            "thread_id": thread_id,
            "terminal_id": terminal_id,
            "lease_id": lease_id,
            "runtime_id": runtime_id,
            "status": status,
            "idle_ttl_sec": idle_ttl_sec,
            "max_duration_sec": max_duration_sec,
            "budget_json": budget_json,
            "started_at": now_iso,
            "last_active_at": last_active,
            "ended_at": None,
            "close_reason": None,
        }

    def touch(self, session_id: str, last_active_at: str | None = None, status: str | None = None) -> None:
        now = last_active_at or datetime.now().isoformat()
        with self._lock:
            if status is not None:
                self._conn.execute(
                    """
                    UPDATE chat_sessions
                    SET last_active_at = ?, status = ?
                    WHERE chat_session_id = ?
                    """,
                    (now, status, session_id),
                )
            else:
                self._conn.execute(
                    """
                    UPDATE chat_sessions
                    SET last_active_at = ?
                    WHERE chat_session_id = ?
                    """,
                    (now, session_id),
                )
            self._conn.commit()

    def touch_thread_activity(self, thread_id: str, last_active_at: str | None = None) -> None:
        now = last_active_at or datetime.now().isoformat()
        with self._lock:
            self._conn.execute(
                """
                UPDATE chat_sessions
                SET last_active_at = ?
                WHERE thread_id = ? AND status != 'closed'
                """,
                (now, thread_id),
            )
            self._conn.commit()

    def pause(self, session_id: str) -> None:
        with self._lock:
            self._conn.execute(
                """
                UPDATE chat_sessions
                SET status = 'paused', close_reason = 'paused'
                WHERE chat_session_id = ? AND status IN ('active', 'idle')
                """,
                (session_id,),
            )
            self._conn.commit()

    def resume(self, session_id: str) -> None:
        with self._lock:
            self._conn.execute(
                """
                UPDATE chat_sessions
                SET status = 'active', close_reason = NULL
                WHERE chat_session_id = ? AND status = 'paused'
                """,
                (session_id,),
            )
            self._conn.commit()

    def upsert_command(
        self,
        *,
        command_id: str,
        terminal_id: str,
        chat_session_id: str | None,
        command_line: str,
        cwd: str,
        status: str,
        stdout: str,
        stderr: str,
        exit_code: int | None,
        updated_at: str,
        finished_at: str | None,
        created_at: str | None = None,
    ) -> None:
        with self._lock:
            existing = self._conn.execute(
                "SELECT command_id, created_at FROM terminal_commands WHERE command_id = ?",
                (command_id,),
            ).fetchone()
            if existing:
                self._conn.execute(
                    """
                    UPDATE terminal_commands
                    SET status = ?,
                        stdout = ?,
                        stderr = ?,
                        exit_code = ?,
                        updated_at = ?,
                        finished_at = ?
                    WHERE command_id = ?
                    """,
                    (status, stdout, stderr, exit_code, updated_at, finished_at, command_id),
                )
            else:
                self._conn.execute(
                    """
                    INSERT INTO terminal_commands (
                        command_id, terminal_id, chat_session_id, command_line, cwd, status,
                        stdout, stderr, exit_code, created_at, updated_at, finished_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        command_id,
                        terminal_id,
                        chat_session_id,
                        command_line,
                        cwd,
                        status,
                        stdout,
                        stderr,
                        exit_code,
                        created_at or updated_at,
                        updated_at,
                        finished_at,
                    ),
                )
            self._conn.commit()

    def append_command_chunks(
        self,
        *,
        command_id: str,
        stdout_chunks: list[str],
        stderr_chunks: list[str],
        created_at: str,
    ) -> None:
        if not stdout_chunks and not stderr_chunks:
            return
        with self._lock:
            if stdout_chunks:
                self._conn.executemany(
                    """
                    INSERT INTO terminal_command_chunks (command_id, stream, content, created_at)
                    VALUES (?, 'stdout', ?, ?)
                    """,
                    [(command_id, chunk, created_at) for chunk in stdout_chunks],
                )
            if stderr_chunks:
                self._conn.executemany(
                    """
                    INSERT INTO terminal_command_chunks (command_id, stream, content, created_at)
                    VALUES (?, 'stderr', ?, ?)
                    """,
                    [(command_id, chunk, created_at) for chunk in stderr_chunks],
                )
            self._conn.commit()

    def get_command(self, *, command_id: str, terminal_id: str) -> dict[str, Any] | None:
        with self._lock:
            self._conn.row_factory = sqlite3.Row
            row = self._conn.execute(
                """
                SELECT command_id, terminal_id, chat_session_id, command_line, cwd, status, stdout, stderr, exit_code,
                       created_at, updated_at, finished_at
                FROM terminal_commands
                WHERE command_id = ? AND terminal_id = ?
                """,
                (command_id, terminal_id),
            ).fetchone()
            self._conn.row_factory = None
            return dict(row) if row else None

    def list_command_chunks(self, *, command_id: str) -> list[dict[str, Any]]:
        with self._lock:
            self._conn.row_factory = sqlite3.Row
            rows = self._conn.execute(
                """
                SELECT stream, content
                FROM terminal_command_chunks
                WHERE command_id = ?
                ORDER BY chunk_id ASC
                """,
                (command_id,),
            ).fetchall()
            self._conn.row_factory = None
            return [dict(row) for row in rows]

    def find_command_terminal_id(self, *, command_id: str, thread_id: str) -> str | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT tc.terminal_id
                FROM terminal_commands tc
                JOIN abstract_terminals at ON at.terminal_id = tc.terminal_id
                WHERE tc.command_id = ? AND at.thread_id = ?
                LIMIT 1
                """,
                (command_id, thread_id),
            ).fetchone()
            return str(row[0]) if row else None

    def delete_session(self, session_id: str, *, reason: str = "closed") -> None:
        with self._lock:
            self._conn.execute(
                """
                UPDATE chat_sessions
                SET status = 'closed', ended_at = ?, close_reason = ?
                WHERE chat_session_id = ? AND status IN ('active', 'idle', 'paused')
                """,
                (datetime.now().isoformat(), reason, session_id),
            )
            self._conn.commit()

    def delete_by_thread(self, thread_id: str) -> None:
        with self._lock:
            rows = self._conn.execute(
                "SELECT command_id FROM terminal_commands WHERE terminal_id IN (SELECT terminal_id FROM abstract_terminals WHERE thread_id = ?)",  # noqa: E501
                (thread_id,),
            ).fetchall()
            if rows:
                command_ids = [str(row[0]) for row in rows]
                placeholders = ",".join("?" for _ in command_ids)
                self._conn.execute(
                    f"DELETE FROM terminal_command_chunks WHERE command_id IN ({placeholders})",
                    command_ids,
                )
            self._conn.execute(
                "DELETE FROM terminal_commands WHERE terminal_id IN (SELECT terminal_id FROM abstract_terminals WHERE thread_id = ?)",
                (thread_id,),
            )
            self._conn.execute("DELETE FROM chat_sessions WHERE thread_id = ?", (thread_id,))
            self._conn.commit()

    def terminal_has_running_command(self, terminal_id: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT 1
                FROM terminal_commands
                WHERE terminal_id = ? AND status = 'running'
                LIMIT 1
                """,
                (terminal_id,),
            ).fetchone()
            return row is not None

    def lease_has_running_command(self, lease_id: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT 1
                FROM terminal_commands tc
                JOIN abstract_terminals at ON at.terminal_id = tc.terminal_id
                WHERE at.lease_id = ? AND tc.status = 'running'
                LIMIT 1
                """,
                (lease_id,),
            ).fetchone()
            return row is not None

    def close_all_active(self, reason: str, ended_at: str | None = None) -> None:
        ts = ended_at or datetime.now().isoformat()
        with self._lock:
            self._conn.execute(
                """
                UPDATE chat_sessions
                SET status = 'closed', ended_at = ?, close_reason = ?
                WHERE status IN ('active', 'idle', 'paused')
                """,
                (ts, reason),
            )
            self._conn.commit()

    def cleanup_expired(self) -> list[str]:
        """Return session_ids of expired active sessions (based on DB policy columns)."""
        active = self.list_active()
        now = datetime.now()
        expired_ids: list[str] = []
        for session in active:
            started_at = datetime.fromisoformat(session["started_at"])
            last_active_at = datetime.fromisoformat(session["last_active_at"])
            idle_ttl_sec = session.get("idle_ttl_sec", 0)
            max_duration_sec = session.get("max_duration_sec", 0)
            policy = self.get_session_policy(session["session_id"])
            if policy:
                idle_ttl_sec = policy["idle_ttl_sec"]
                max_duration_sec = policy["max_duration_sec"]
            idle_elapsed = (now - last_active_at).total_seconds()
            total_elapsed = (now - started_at).total_seconds()
            if idle_elapsed > idle_ttl_sec or total_elapsed > max_duration_sec:
                expired_ids.append(session["session_id"])
        return expired_ids
