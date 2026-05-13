"""Pure user-ownership predicates for chat-related identity checks."""

from __future__ import annotations

from typing import Any


def is_owned_by_viewer(viewer_user_id: str, candidate_user: Any | None) -> bool:
    return candidate_user is not None and (
        getattr(candidate_user, "id", None) == viewer_user_id
        or getattr(candidate_user, "owner_user_id", None) == viewer_user_id
        or getattr(candidate_user, "created_by_user_id", None) == viewer_user_id
    )


def access_scope_targets(candidate_user: Any | None, user_id: str) -> list[str]:
    targets = [user_id]
    if candidate_user is not None:
        for attr in ("owner_user_id", "created_by_user_id"):
            owner_id = getattr(candidate_user, attr, None)
            if owner_id:
                targets.append(str(owner_id))
    return list(dict.fromkeys(targets))


def shares_ownership_scope(left_user: Any | None, right_user: Any | None) -> bool:
    if left_user is None or right_user is None:
        return False
    left_id = str(getattr(left_user, "id", "") or "")
    right_id = str(getattr(right_user, "id", "") or "")
    if not left_id or not right_id:
        return False
    return bool(set(access_scope_targets(left_user, user_id=left_id)) & set(access_scope_targets(right_user, user_id=right_id)))
