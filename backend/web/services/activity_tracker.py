"""Activity tracking for session lifecycle management.

Decouples activity sources (file uploads, API calls) from session management.
"""

import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def track_thread_activity(thread_id: str, activity_type: str = "activity") -> None:
    """Update session activity timestamp for a thread.

    # @@@raw-sql-touch - Bypasses ChatSession.touch() intentionally:
    # workspace_service has no access to ChatSession objects, and we only need
    # to bump last_active_at to prevent idle reaper from pausing during file uploads.
    # Does NOT change session status — preserves paused/active state as-is.
    """
    from sandbox.config import DEFAULT_DB_PATH
    from storage.providers.sqlite.kernel import connect_sqlite

    now = datetime.now().isoformat()
    with connect_sqlite(DEFAULT_DB_PATH) as conn:
        conn.execute(
            "UPDATE chat_sessions SET last_active_at = ? WHERE thread_id = ? AND status != 'closed'",
            (now, thread_id),
        )
        conn.commit()

