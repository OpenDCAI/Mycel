"""Agent Registry — Supabase-backed agent_id -> thread_id mapping.

@@@id-based — all lookups use agent_id, never name.
Name is stored for display only.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any


@dataclass
class AgentEntry:
    agent_id: str
    name: str
    thread_id: str
    status: str
    parent_agent_id: str | None = None
    subagent_type: str | None = None


class _InMemoryAgentRegistryRepo:
    def __init__(self) -> None:
        self._rows: dict[str, tuple[str, str, str, str, str | None, str | None]] = {}

    def register(
        self,
        *,
        agent_id: str,
        name: str,
        thread_id: str,
        status: str,
        parent_agent_id: str | None,
        subagent_type: str | None,
    ) -> None:
        self._rows[agent_id] = (agent_id, name, thread_id, status, parent_agent_id, subagent_type)

    def get_by_id(self, agent_id: str) -> tuple[str, str, str, str, str | None, str | None] | None:
        return self._rows.get(agent_id)

    def list_running_by_name(self, name: str) -> list[tuple[str, str, str, str, str | None, str | None]]:
        return [row for row in self._rows.values() if row[1] == name and row[3] == "running"]

    def update_status(self, agent_id: str, status: str) -> None:
        row = self._rows.get(agent_id)
        if row is None:
            return
        self._rows[agent_id] = (row[0], row[1], row[2], status, row[4], row[5])

    def remove(self, agent_id: str) -> None:
        self._rows.pop(agent_id, None)

    def list_running(self) -> list[tuple[str, str, str, str, str | None, str | None]]:
        return [row for row in self._rows.values() if row[3] == "running"]


class AgentRegistry:
    """Registry mapping agent_ids to thread IDs."""

    def __init__(self, repo: Any = None):
        self._lock = asyncio.Lock()
        self._repo = repo or _InMemoryAgentRegistryRepo()

    async def register(self, entry: AgentEntry) -> None:
        async with self._lock:
            self._repo.register(
                agent_id=entry.agent_id,
                name=entry.name,
                thread_id=entry.thread_id,
                status=entry.status,
                parent_agent_id=entry.parent_agent_id,
                subagent_type=entry.subagent_type,
            )

    async def list_running_by_name(self, name: str) -> list[AgentEntry]:
        rows = self._repo.list_running_by_name(name)
        return [
            AgentEntry(
                agent_id=row[0],
                name=row[1],
                thread_id=row[2],
                status=row[3],
                parent_agent_id=row[4],
                subagent_type=row[5],
            )
            for row in rows
        ]

    async def remove(self, agent_id: str) -> None:
        async with self._lock:
            self._repo.remove(agent_id)
