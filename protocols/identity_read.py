"""Identity read-side protocol contracts."""

from __future__ import annotations

from typing import Any, Protocol


class DisplayUserLookup(Protocol):
    def get_by_id(self, social_user_id: str) -> Any | None: ...


class UserDirectory(Protocol):
    def get_by_id(self, social_user_id: str) -> Any | None: ...

    def list_by_ids(self, user_ids: list[str]) -> list[Any]: ...

    def list_all(self) -> list[Any]: ...


class AgentActorLookup(Protocol):
    def is_agent_actor_user(self, social_user_id: str) -> bool: ...
