"""Active-agent registry — tracks spawned agents by id and name."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class AgentEntry:
    name: str
    task_id: str
    status: str = "running"  # running | done | error
    result: dict[str, Any] | None = None


class AgentRegistry:
    def __init__(self) -> None:
        self._by_id: dict[str, AgentEntry] = {}
        self._by_name: dict[str, AgentEntry] = {}

    def register(self, entry: AgentEntry) -> None:
        self._by_id[entry.task_id] = entry
        self._by_name[entry.name] = entry

    def by_id(self, task_id: str) -> AgentEntry | None:
        return self._by_id.get(task_id)

    def by_name(self, name: str) -> AgentEntry | None:
        return self._by_name.get(name)

    def names(self) -> list[str]:
        return list(self._by_name)
