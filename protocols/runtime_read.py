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


class RuntimeThreadActivityReader(Protocol):
    def list_active_threads_for_agent(self, agent_user_id: str) -> list[AgentThreadActivity]: ...
