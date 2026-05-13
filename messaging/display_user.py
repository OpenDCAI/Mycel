from __future__ import annotations

from typing import Any


def resolve_messaging_display_user(*, user_repo: Any, social_user_id: str) -> Any | None:
    return user_repo.get_by_id(social_user_id)
