"""Shared avatar URL helpers."""

from __future__ import annotations

from backend.web.core.paths import avatars_dir


def avatar_url(user_id: str | None, has_avatar: bool) -> str | None:
    """Build avatar URL. Returns None if no avatar uploaded."""
    # @@@avatar-truth-seam - current web avatar serving is file-backed; DB avatar
    # rows may legitimately stay null on the Supabase path, so visibility truth
    # must follow the actual served file surface instead of trusting the column alone.
    if not user_id:
        return None
    if has_avatar or (avatars_dir() / f"{user_id}.png").exists():
        return f"/api/users/{user_id}/avatar"
    return None
