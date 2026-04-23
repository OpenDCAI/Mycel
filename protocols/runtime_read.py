"""Runtime read-side protocol contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass(frozen=True)
class AgentThreadActivity:
    thread_id: str
    is_main: bool
    branch_index: int
    state: Literal["initializing", "ready", "active", "idle", "suspended", "stopped", "destroyed"]


@dataclass(frozen=True)
class HireConversation:
    id: str
    title: str
    avatar_url: str | None
    updated_at: str | None
    running: bool


class RuntimeThreadActivityReader(Protocol):
    def list_active_threads_for_agent(self, agent_user_id: str) -> list[AgentThreadActivity]: ...


class HireConversationReader(Protocol):
    async def list_hire_conversations_for_user(self, user_id: str) -> list[HireConversation]: ...


class AgentActorLookup(Protocol):
    def is_agent_actor_user(self, social_user_id: str) -> bool: ...
