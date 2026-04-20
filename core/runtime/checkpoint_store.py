from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ThreadCheckpointState:
    messages: list
    tool_permission_context: dict[str, Any]
    pending_permission_requests: dict[str, dict[str, Any]]
    resolved_permission_requests: dict[str, dict[str, Any]]
    memory_compaction_state: dict[str, Any]
    mcp_instruction_state: dict[str, Any]


class CheckpointStore(Protocol):
    async def load(self, thread_id: str) -> ThreadCheckpointState | None: ...

    async def save(self, thread_id: str, state: ThreadCheckpointState) -> None: ...
