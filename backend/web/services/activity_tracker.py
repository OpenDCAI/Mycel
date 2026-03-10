"""Activity tracking for session lifecycle management.

Decouples activity sources (file uploads, API calls) from session management.
"""

import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


def track_thread_activity(thread_id: str, activity_type: str = "activity") -> None:
    """Update session activity timestamp for a thread.

    Args:
        thread_id: Thread identifier
        activity_type: Type of activity (for logging/debugging)
    """
    try:
        from sandbox.config import DEFAULT_DB_PATH
        from storage.providers.sqlite.kernel import connect_sqlite

        now = datetime.now().isoformat()
        with connect_sqlite(DEFAULT_DB_PATH) as conn:
            conn.execute(
                "UPDATE chat_sessions SET last_active_at = ? WHERE thread_id = ? AND status != 'closed'",
                (now, thread_id),
            )
            conn.commit()
    except Exception as e:
        logger.warning(f"Failed to track {activity_type} for thread {thread_id}: {e}")

