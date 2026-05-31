"""In-memory CheckpointStore — the zero-dependency default.

Holds per-thread state in a dict. Lost on process exit; for durability use a
sqlite or Postgres adapter implementing the same ``CheckpointStore`` port.
"""

from __future__ import annotations

from agent_core.ports.checkpoint import CheckpointStore, ThreadCheckpointState


class InMemoryCheckpointStore(CheckpointStore):
    def __init__(self) -> None:
        self._threads: dict[str, ThreadCheckpointState] = {}

    async def load(self, thread_id: str) -> ThreadCheckpointState | None:
        return self._threads.get(thread_id)

    async def save(self, thread_id: str, state: ThreadCheckpointState) -> None:
        self._threads[thread_id] = state
