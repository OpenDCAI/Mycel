from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from pathlib import Path

from storage.contracts import NotificationType, QueueItem, QueueRepo
from storage.runtime import build_queue_repo, uses_supabase_runtime_defaults

logger = logging.getLogger(__name__)


class MessageQueueManager:
    def __init__(self, repo: QueueRepo | None = None, *, db_path: str | None = None) -> None:
        if repo is not None:
            self._repo = repo
        elif db_path is None and uses_supabase_runtime_defaults():
            self._repo = build_queue_repo()
        else:
            from storage.providers.sqlite.queue_repo import SQLiteQueueRepo

            resolved = Path(db_path) if db_path else None
            self._repo = SQLiteQueueRepo(db_path=resolved)
        # Expose db_path for diagnostics / tests
        self._db_path: str = getattr(self._repo, "_db_path", "")
        self._wake_handlers: dict[str, Callable[[QueueItem], None]] = {}
        self._wake_lock = threading.Lock()

    def enqueue(
        self,
        content: str,
        thread_id: str,
        notification_type: NotificationType = "steer",
        source: str | None = None,
        sender_id: str | None = None,
        sender_name: str | None = None,
        sender_avatar_url: str | None = None,
        is_steer: bool = False,
    ) -> None:
        self._repo.enqueue(
            thread_id,
            content,
            notification_type,
            source=source,
            sender_id=sender_id,
            sender_name=sender_name,
        )
        with self._wake_lock:
            handler = self._wake_handlers.get(thread_id)
        if handler:
            try:
                handler(
                    QueueItem(
                        content=content,
                        notification_type=notification_type,
                        source=source,
                        sender_id=sender_id,
                        sender_name=sender_name,
                        sender_avatar_url=sender_avatar_url,
                        is_steer=is_steer,
                    )
                )
            except Exception:
                logger.exception("Wake handler raised for thread %s", thread_id)

    def dequeue(self, thread_id: str) -> QueueItem | None:
        return self._repo.dequeue(thread_id)

    def drain_all(self, thread_id: str) -> list[QueueItem]:
        return self._repo.drain_all(thread_id)

    def peek(self, thread_id: str) -> bool:
        return self._repo.peek(thread_id)

    def list_queue(self, thread_id: str) -> list[dict]:
        return self._repo.list_queue(thread_id)

    def register_wake(self, thread_id: str, handler: Callable[[QueueItem], None]) -> None:
        with self._wake_lock:
            self._wake_handlers[thread_id] = handler

    def unregister_wake(self, thread_id: str) -> None:
        with self._wake_lock:
            self._wake_handlers.pop(thread_id, None)

    def clear_queue(self, thread_id: str) -> None:
        self._repo.clear_queue(thread_id)

    def clear_all(self, thread_id: str) -> None:
        self.clear_queue(thread_id)
        self.unregister_wake(thread_id)

    def queue_sizes(self, thread_id: str) -> dict[str, int]:
        return {"followup": self._repo.count(thread_id)}
