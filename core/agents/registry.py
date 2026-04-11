"""Agent Registry — Supabase-backed agent_id -> thread_id mapping.

@@@id-based — all lookups use agent_id, never name.
Name is stored for display only.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from storage.runtime import build_agent_registry_repo


@dataclass
class AgentEntry:
    agent_id: str
    name: str
    thread_id: str
    status: str
    parent_agent_id: str | None = None
    subagent_type: str | None = None


class AgentRegistry:
    """Supabase-backed registry mapping agent_ids to thread IDs."""

    def __init__(self, repo: Any = None):
        self._lock = asyncio.Lock()
        self._repo = repo or build_agent_registry_repo()

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

    async def get_by_id(self, agent_id: str) -> AgentEntry | None:
        row = self._repo.get_by_id(agent_id)
        if row is None:
            return None
        return AgentEntry(
            agent_id=row[0],
            name=row[1],
            thread_id=row[2],
            status=row[3],
            parent_agent_id=row[4],
            subagent_type=row[5],
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

    async def get_latest_by_name_and_parent(self, name: str, parent_agent_id: str | None) -> AgentEntry | None:
        row = self._repo.get_latest_by_name_and_parent(name, parent_agent_id)
        if row is None:
            return None
        return AgentEntry(
            agent_id=row[0],
            name=row[1],
            thread_id=row[2],
            status=row[3],
            parent_agent_id=row[4],
            subagent_type=row[5],
        )

    async def update_status(self, agent_id: str, status: str) -> None:
        async with self._lock:
            self._repo.update_status(agent_id, status)

    async def list_running(self) -> list[AgentEntry]:
        rows = self._repo.list_running()
        return [
            AgentEntry(
                agent_id=r[0],
                name=r[1],
                thread_id=r[2],
                status=r[3],
                parent_agent_id=r[4],
                subagent_type=r[5],
            )
            for r in rows
        ]
