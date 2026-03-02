"""Message Queue Manager — unified SQLite message queue.

Single channel: all messages go through SQLite (enqueue/dequeue/drain_all).
Wake handlers notify the host when messages arrive for idle agents.
"""

import logging
import sqlite3
import threading
from collections.abc import Callable
from pathlib import Path

logger = logging.getLogger(__name__)


class MessageQueueManager:
    """Unified SQLite message queue with wake-on-enqueue support."""

    def __init__(self, db_path: str | None = None):
        self._db_path = db_path or str(Path.home() / ".leon" / "leon.db")
        self._wake_handlers: dict[str, Callable[[], None]] = {}
        self._wake_lock = threading.Lock()
        self._ensure_table()

    # ------------------------------------------------------------------
    # SQLite setup
    # ------------------------------------------------------------------

    def _ensure_table(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS message_queue ("
                "  id         INTEGER PRIMARY KEY AUTOINCREMENT,"
                "  thread_id  TEXT NOT NULL,"
                "  content    TEXT NOT NULL,"
                "  created_at TEXT DEFAULT (datetime('now'))"
                ")"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_mq_thread ON message_queue (thread_id, id)"
            )
            conn.commit()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def enqueue(self, content: str, thread_id: str) -> None:
        """Persist a message. Fires wake handler after INSERT."""
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO message_queue (thread_id, content) VALUES (?, ?)",
                (thread_id, content),
            )
            conn.commit()
        # Fire wake handler OUTSIDE DB transaction
        with self._wake_lock:
            handler = self._wake_handlers.get(thread_id)
        if handler:
            try:
                handler()
            except Exception:
                logger.exception("Wake handler raised for thread %s", thread_id)

    def dequeue(self, thread_id: str) -> str | None:
        """Atomically pop the oldest message (DELETE + RETURNING)."""
        with self._conn() as conn:
            row = conn.execute(
                "DELETE FROM message_queue "
                "WHERE id = (SELECT MIN(id) FROM message_queue WHERE thread_id = ?) "
                "RETURNING content",
                (thread_id,),
            ).fetchone()
            conn.commit()
            return row["content"] if row else None

    def drain_all(self, thread_id: str) -> list[str]:
        """Atomically DELETE all pending messages, return FIFO-ordered list."""
        with self._conn() as conn:
            rows = conn.execute(
                "DELETE FROM message_queue WHERE thread_id = ? RETURNING content, id",
                (thread_id,),
            ).fetchall()
            conn.commit()
        return [r["content"] for r in sorted(rows, key=lambda r: r["id"])]

    def peek(self, thread_id: str) -> bool:
        """Check if the queue has messages (without consuming)."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM message_queue WHERE thread_id = ? LIMIT 1",
                (thread_id,),
            ).fetchone()
            return row is not None

    def list_queue(self, thread_id: str) -> list[dict]:
        """List all pending messages (for API queries)."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, content, created_at FROM message_queue "
                "WHERE thread_id = ? ORDER BY id",
                (thread_id,),
            ).fetchall()
            return [{"id": r["id"], "content": r["content"], "created_at": r["created_at"]} for r in rows]

    # ------------------------------------------------------------------
    # Wake handler registration
    # ------------------------------------------------------------------

    def register_wake(self, thread_id: str, handler: Callable[[], None]) -> None:
        """Register a wake handler for a thread. Called by enqueue() after INSERT."""
        with self._wake_lock:
            self._wake_handlers[thread_id] = handler

    def unregister_wake(self, thread_id: str) -> None:
        """Remove wake handler for a thread."""
        with self._wake_lock:
            self._wake_handlers.pop(thread_id, None)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def clear_queue(self, thread_id: str) -> None:
        """Clear persisted queue for a thread."""
        with self._conn() as conn:
            conn.execute("DELETE FROM message_queue WHERE thread_id = ?", (thread_id,))
            conn.commit()

    def clear_all(self, thread_id: str) -> None:
        """Clear queue and unregister wake handler for a thread."""
        self.clear_queue(thread_id)
        self.unregister_wake(thread_id)

    def clear_thread(self, thread_id: str) -> None:
        """Alias for clear_all (backward compat)."""
        self.clear_all(thread_id)

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def queue_sizes(self, thread_id: str) -> dict[str, int]:
        """Return queue sizes. steer is always 0 (backward compat)."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM message_queue WHERE thread_id = ?",
                (thread_id,),
            ).fetchone()
            followup_size = row["cnt"] if row else 0
        return {"steer": 0, "followup": followup_size}
