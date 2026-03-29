"""Message Queue Manager — facade over QueueRepo with wake-on-enqueue.

Delegates all persistence to a QueueRepo (storage layer).
Wake handlers notify the host when messages arrive for idle agents.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from pathlib import Path

from storage.contracts import QueueItem, QueueRepo

logger = logging.getLogger(__name__)


class MessageQueueManager:
    """Facade: QueueRepo persistence + wake handler orchestration."""

    def __init__(self, repo: QueueRepo | None = None, *, db_path: str | None = None) -> None:
        if repo is not None:
            self._repo = repo
        else:
            from storage.providers.sqlite.queue_repo import SQLiteQueueRepo
            resolved = Path(db_path) if db_path else None
            self._repo = SQLiteQueueRepo(db_path=resolved)
        # Expose db_path for diagnostics / tests
        self._db_path: str = getattr(self._repo, "_db_path", "")
        self._wake_handlers: dict[str, Callable[["QueueItem"], None]] = {}
        self._wake_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def enqueue(self, content: str, thread_id: str, notification_type: str = "steer",
                source: str | None = None, sender_entity_id: str | None = None,
                sender_name: str | None = None, sender_avatar_url: str | None = None,
                is_steer: bool = False, extra_metadata: dict | None = None) -> None:
        """Persist a message. Fires wake handler after INSERT."""
        self._repo.enqueue(thread_id, content, notification_type,
                           source=source, sender_entity_id=sender_entity_id, sender_name=sender_name,
                           extra_metadata=extra_metadata)
        with self._wake_lock:
            handler = self._wake_handlers.get(thread_id)
        if handler:
            try:
                handler(QueueItem(content=content, notification_type=notification_type,
                                  source=source, sender_entity_id=sender_entity_id,
                                  sender_name=sender_name, sender_avatar_url=sender_avatar_url,
                                  is_steer=is_steer, extra_metadata=extra_metadata))
            except Exception:
                logger.exception("Wake handler raised for thread %s", thread_id)

    def dequeue(self, thread_id: str) -> QueueItem | None:
        """Atomically pop the oldest message."""
        return self._repo.dequeue(thread_id)

    def drain_all(self, thread_id: str) -> list[QueueItem]:
        """Atomically pop all pending messages, return FIFO-ordered list."""
        return self._repo.drain_all(thread_id)

    def peek(self, thread_id: str) -> bool:
        """Check if the queue has messages (without consuming)."""
        return self._repo.peek(thread_id)

    def list_queue(self, thread_id: str) -> list[dict]:
        """List all pending messages (for API queries)."""
        return self._repo.list_queue(thread_id)

    # ------------------------------------------------------------------
    # Wake handler registration
    # ------------------------------------------------------------------

    def register_wake(self, thread_id: str, handler: Callable[["QueueItem"], None]) -> None:
        """Register a wake handler for a thread.

        The handler receives the newly-enqueued QueueItem.
        Called by enqueue() after INSERT.
        """
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
        self._repo.clear_queue(thread_id)

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
        return {"steer": 0, "followup": self._repo.count(thread_id)}
