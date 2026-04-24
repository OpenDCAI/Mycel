"""Pure user-ownership predicates for chat-related identity checks."""

from __future__ import annotations

from typing import Any


def is_owned_by_viewer(viewer_user_id: str, candidate_user: Any | None) -> bool:
    return candidate_user is not None and (
        getattr(candidate_user, "id", None) == viewer_user_id or getattr(candidate_user, "owner_user_id", None) == viewer_user_id
    )


def access_scope_targets(candidate_user: Any | None, user_id: str) -> list[str]:
    owner_user_id = getattr(candidate_user, "owner_user_id", None) if candidate_user is not None else None
    return [user_id, str(owner_user_id)] if owner_user_id else [user_id]
