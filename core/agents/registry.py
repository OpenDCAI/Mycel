"""Agent registry shared row types."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AgentEntry:
    agent_id: str
    name: str
    thread_id: str
    status: str
    parent_agent_id: str | None = None
    subagent_type: str | None = None
