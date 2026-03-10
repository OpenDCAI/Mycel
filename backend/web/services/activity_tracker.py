"""Activity tracking for session lifecycle management.

Decouples activity sources (file uploads, API calls) from session management.
"""

import logging

logger = logging.getLogger(__name__)


def track_thread_activity(thread_id: str, activity_type: str = "activity") -> None:
    """Update session activity timestamp for a thread.

    Args:
        thread_id: Thread identifier
        activity_type: Type of activity (for logging/debugging)
    """
    try:
        from backend.web.utils.helpers import _get_container
        mgr = _get_container().sandbox_manager()
        session = mgr.session_manager.get_by_thread(thread_id)
        if session:
            session.touch()
    except Exception as e:
        logger.warning(f"Failed to track {activity_type} for thread {thread_id}: {e}")
