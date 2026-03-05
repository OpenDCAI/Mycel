"""SummaryStore - Persistent storage for conversation summaries.

This module implements persistent storage for MemoryMiddleware summaries,
preventing loss of cached summaries across restarts.

Architecture:
    MemoryMiddleware → SummaryStore → SQLite
    - Summaries stored with thread_id as key
    - Only latest summary per thread is active
    - Historical summaries retained for audit
"""

from __future__ import annotations

import logging
import sqlite3
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from storage.contracts import SummaryRepo, SummaryRow
from storage.providers.sqlite.kernel import connect_sqlite

from storage.providers.sqlite.summary_repo import SQLiteSummaryRepo

logger = logging.getLogger(__name__)


def _connect(db_path: Path) -> sqlite3.Connection:
    """Create SQLite connection with proper timeout settings."""
    return connect_sqlite(db_path)


@dataclass
class SummaryData:
    """Summary data snapshot.

    Represents a conversation summary that persists across sessions.
    """

    summary_id: str
    thread_id: str
    summary_text: str
    compact_up_to_index: int
    compacted_at: int
    is_split_turn: bool = False
    split_turn_prefix: str | None = None
    is_active: bool = True
    created_at: str | None = None


class SummaryStore:
    """Store for managing conversation summary persistence.

    Handles CRUD operations for summaries in the database.
    Follows the same pattern as TerminalStore for consistency.
    """

    def __init__(self, db_path: Path | None = None, summary_repo: SummaryRepo | None = None):
        if db_path is None and summary_repo is None:
            raise ValueError("SummaryStore requires either db_path or summary_repo")
        self.db_path = db_path
        self._repo: SummaryRepo
        if summary_repo is not None:
            self._repo = summary_repo
        else:
            # @@@connect_injection - keep _connect as an indirection point so existing retry/rollback tests can patch it.
            self._repo = SQLiteSummaryRepo(db_path, connect_fn=lambda p: _connect(p))
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        """Ensure summaries table exists."""
        self._repo.ensure_tables()

    def save_summary(
        self,
        thread_id: str,
        summary_text: str,
        compact_up_to_index: int,
        compacted_at: int,
        is_split_turn: bool = False,
        split_turn_prefix: str | None = None,
        max_retries: int = 3,
    ) -> str:
        """Save a new summary and mark old summaries as inactive.

        Args:
            thread_id: Thread identifier
            summary_text: The summary content
            compact_up_to_index: Index up to which messages were compacted
            compacted_at: Total message count when compaction occurred
            is_split_turn: Whether this is a split turn summary
            split_turn_prefix: Optional prefix summary for split turns
            max_retries: Maximum number of retry attempts on failure

        Returns:
            summary_id: The generated summary ID

        Raises:
            sqlite3.Error: If save fails after all retries
        """
        summary_id = f"{thread_id}_{uuid.uuid4().hex[:12]}"
        now = datetime.now().isoformat()

        for attempt in range(max_retries):
            try:
                self._repo.save_summary(
                    summary_id=summary_id,
                    thread_id=thread_id,
                    summary_text=summary_text,
                    compact_up_to_index=compact_up_to_index,
                    compacted_at=compacted_at,
                    is_split_turn=is_split_turn,
                    split_turn_prefix=split_turn_prefix,
                    created_at=now,
                )

                logger.info(f"[SummaryStore] Saved summary {summary_id} for thread {thread_id}")
                return summary_id

            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"[SummaryStore] Save failed (attempt {attempt + 1}/{max_retries}): {e}")
                    time.sleep(0.1 * (attempt + 1))  # Exponential backoff
                else:
                    logger.error(f"[SummaryStore] Save failed after {max_retries} attempts: {e}")
                    raise

    def get_latest_summary(
        self,
        thread_id: str,
        max_retries: int = 3,
    ) -> SummaryData | None:
        """Get the latest active summary for a thread.

        Args:
            thread_id: Thread identifier
            max_retries: Maximum number of retry attempts on failure

        Returns:
            SummaryData if found, None if no summary exists or data is corrupted
        """
        for attempt in range(max_retries):
            try:
                row: SummaryRow | None = self._repo.get_latest_summary_row(thread_id)

                if not row:
                    return None

                # Validate data integrity
                try:
                    return SummaryData(
                        summary_id=row["summary_id"],
                        thread_id=row["thread_id"],
                        summary_text=row["summary_text"],
                        compact_up_to_index=row["compact_up_to_index"],
                        compacted_at=row["compacted_at"],
                        is_split_turn=bool(row["is_split_turn"]),
                        split_turn_prefix=row["split_turn_prefix"],
                        is_active=bool(row["is_active"]),
                        created_at=row["created_at"],
                    )
                except (KeyError, TypeError, ValueError) as e:
                    logger.error(f"[SummaryStore] Data corruption detected: {e}")
                    return None  # Signal data corruption

            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"[SummaryStore] Read failed (attempt {attempt + 1}/{max_retries}): {e}")
                    time.sleep(0.1 * (attempt + 1))  # Exponential backoff
                else:
                    logger.error(f"[SummaryStore] Read failed after {max_retries} attempts: {e}")
                    return None  # Signal failure

        return None

    def list_summaries(self, thread_id: str) -> list[dict[str, Any]]:
        """List all summaries for a thread (for audit purposes).

        Args:
            thread_id: Thread identifier

        Returns:
            List of summary records as dictionaries
        """
        return self._repo.list_summaries(thread_id)

    def delete_thread_summaries(self, thread_id: str) -> None:
        """Delete all summaries for a thread.

        Args:
            thread_id: Thread identifier
        """
        self._repo.delete_thread_summaries(thread_id)

        logger.info(f"[SummaryStore] Deleted all summaries for thread {thread_id}")
