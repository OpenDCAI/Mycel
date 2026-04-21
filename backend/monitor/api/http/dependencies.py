"""Monitor router dependency helpers."""

from __future__ import annotations

from backend.identity.auth.user_resolution import get_current_user_id
from backend.runtime_bootstrap.request_app import get_app

__all__ = ["get_app", "get_current_user_id"]
