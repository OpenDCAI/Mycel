"""Activity tracking for session lifecycle management.

Decouples activity sources (file uploads, API calls) from session management.
"""

import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def track_thread_activity(thread_id: str, activity_type: str = "activity") -> None:
    """Update session activity timestamp for a thread.

    # @@@raw-sql-touch - Bypasses ChatSession.touch() intentionally:
    # activity_tracker has no access to ChatSession objects, and we only need
    # to bump last_active_at to prevent idle reaper from pausing during file uploads.
    # Does NOT change session status — preserves paused/active state as-is.
    """
    from storage.providers.sqlite.kernel import SQLiteDBRole, connect_sqlite, resolve_role_db_path

    now = datetime.now().isoformat()
    with connect_sqlite(resolve_role_db_path(SQLiteDBRole.SANDBOX)) as conn:
        conn.execute(
            "UPDATE chat_sessions SET last_active_at = ? WHERE thread_id = ? AND status != 'closed'",
            (now, thread_id),
        )
        conn.commit()

