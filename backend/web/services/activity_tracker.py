"""Activity tracking for session lifecycle management.

Decouples activity sources (file uploads, API calls) from session management.
"""

import logging

from sandbox.clock import utc_now_iso
from storage.runtime import build_chat_session_repo as make_chat_session_repo

logger = logging.getLogger(__name__)


def track_thread_activity(thread_id: str, activity_type: str = "activity") -> None:
    """Update session activity timestamp for a thread.

    # @@@raw-sql-touch - Bypasses ChatSession.touch() intentionally:
    # activity_tracker has no access to ChatSession objects, and we only need
    # to bump last_active_at to prevent idle reaper from pausing during file uploads.
    # Does NOT change session status — preserves paused/active state as-is.
    """
    now = utc_now_iso()
    repo = make_chat_session_repo()
    try:
        repo.touch_thread_activity(thread_id, now)
    finally:
        repo.close()
