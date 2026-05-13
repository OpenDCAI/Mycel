"""Avatar URL protocol for messaging-owned projections."""

from __future__ import annotations

from typing import Protocol


class AvatarUrlBuilder(Protocol):
    def __call__(self, user_id: str | None, has_avatar: bool) -> str | None: ...
