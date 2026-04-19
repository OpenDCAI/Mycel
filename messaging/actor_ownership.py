"""Pure actor-ownership predicates for chat-related identity checks."""

from __future__ import annotations

from typing import Any


def is_owned_by_viewer(viewer_user_id: str, candidate_user: Any | None) -> bool:
    return candidate_user is not None and (
        getattr(candidate_user, "id", None) == viewer_user_id or getattr(candidate_user, "owner_user_id", None) == viewer_user_id
    )


def access_scope_targets(actor_user: Any | None, fallback_actor_id: str) -> list[str]:
    owner_user_id = getattr(actor_user, "owner_user_id", None) if actor_user is not None else None
    return [fallback_actor_id, str(owner_user_id)] if owner_user_id else [fallback_actor_id]
