from __future__ import annotations


def avatar_url(user_id: str | None, has_avatar: bool) -> str | None:
    if not user_id:
        return None
    if has_avatar:
        return f"/api/users/{user_id}/avatar"
    return None
