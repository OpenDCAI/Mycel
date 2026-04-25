from __future__ import annotations

from config.agent_config_types import AgentSnapshot, ResolvedAgentConfig


def snapshot_from_resolved_config(config: ResolvedAgentConfig) -> AgentSnapshot:
    return AgentSnapshot(agent=config)
