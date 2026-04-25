"""Supabase repository for AgentConfig aggregates."""

from __future__ import annotations

from typing import Any

from config.agent_config_resolver import resolve_agent_config, validate_agent_skill_content
from config.agent_config_types import AgentConfig, AgentRule, AgentSkill, AgentSubAgent, McpServerConfig
from storage.providers.supabase import _query as q

_REPO = "agent_config repo"
_SCHEMA = "agent"


def _reject_duplicate_names(label: str, names: list[str]) -> None:
    seen: set[str] = set()
    for name in names:
        if name in seen:
            raise ValueError(f"Duplicate {label} name in AgentConfig: {name}")
        seen.add(name)


def _reject_duplicate_child_names(config: AgentConfig) -> None:
    _reject_duplicate_names("Skill", [skill.name for skill in config.skills])
    _reject_duplicate_names("Rule", [rule.name for rule in config.rules])
    _reject_duplicate_names("SubAgent", [agent.name for agent in config.sub_agents])
    _reject_duplicate_names("MCP server", [server.name for server in config.mcp_servers])


class SupabaseAgentConfigRepo:
    def __init__(self, client: Any) -> None:
        self._client = q.validate_client(client, _REPO)

    def close(self) -> None:
        return None

    def _table(self, table: str) -> Any:
        return q.schema_table(self._client, _SCHEMA, table, _REPO)

    def get_agent_config(self, agent_config_id: str) -> AgentConfig | None:
        rows = q.rows(
            self._table("agent_configs").select("*").eq("id", agent_config_id).execute(),
            _REPO,
            "get_agent_config",
        )
        if not rows:
            return None
        root = dict(rows[0])
        return AgentConfig(
            id=root["id"],
            owner_user_id=root["owner_user_id"],
            agent_user_id=root["agent_user_id"],
            name=root["name"],
            description=root.get("description") or "",
            model=root.get("model"),
            tools=list(root.get("tools_json") or ["*"]),
            system_prompt=root.get("system_prompt") or "",
            status=root.get("status") or "draft",
            version=root.get("version") or "0.1.0",
            runtime_settings=dict(root.get("runtime_json") or {}),
            compact=dict(root.get("compact_json") or {}),
            meta=dict(root.get("meta_json") or {}),
            skills=self._list_skill_rows(agent_config_id),
            rules=self._list_rule_rows(agent_config_id),
            sub_agents=self._list_sub_agent_rows(agent_config_id),
            mcp_servers=self._list_mcp_rows(agent_config_id),
        )

    def save_agent_config(self, config: AgentConfig) -> None:
        _reject_duplicate_child_names(config)
        resolve_agent_config(config)
        for skill in config.skills:
            validate_agent_skill_content(skill)
        payload = config.model_dump(mode="json")
        q.schema_rpc(self._client, _SCHEMA, "save_agent_config", {"payload": payload}, _REPO).execute()

    def delete_agent_config(self, agent_config_id: str) -> None:
        self._table("agent_skills").delete().eq("agent_config_id", agent_config_id).execute()
        self._table("agent_rules").delete().eq("agent_config_id", agent_config_id).execute()
        self._table("agent_sub_agents").delete().eq("agent_config_id", agent_config_id).execute()
        self._table("agent_configs").delete().eq("id", agent_config_id).execute()

    def _list_skill_rows(self, agent_config_id: str) -> list[AgentSkill]:
        rows = q.rows(
            self._table("agent_skills").select("*").eq("agent_config_id", agent_config_id).execute(),
            _REPO,
            "_list_skill_rows",
        )
        return [
            AgentSkill(
                id=row.get("id"),
                skill_id=row.get("skill_id"),
                name=row["name"],
                description=row.get("description") or "",
                version=row.get("version") or "0.1.0",
                content=row["content"],
                files=dict(row.get("files_json") or {}),
                enabled=bool(row.get("enabled", True)),
                source=dict(row.get("source_json") or {}),
            )
            for row in rows
        ]

    def _list_rule_rows(self, agent_config_id: str) -> list[AgentRule]:
        rows = q.rows(
            self._table("agent_rules").select("*").eq("agent_config_id", agent_config_id).execute(),
            _REPO,
            "_list_rule_rows",
        )
        return [
            AgentRule(
                id=row.get("id"),
                name=row.get("name") or row.get("filename") or "rule",
                content=row.get("content") or "",
                enabled=bool(row.get("enabled", True)),
            )
            for row in rows
        ]

    def _list_sub_agent_rows(self, agent_config_id: str) -> list[AgentSubAgent]:
        rows = q.rows(
            self._table("agent_sub_agents").select("*").eq("agent_config_id", agent_config_id).execute(),
            _REPO,
            "_list_sub_agent_rows",
        )
        return [
            AgentSubAgent(
                id=row.get("id"),
                name=row["name"],
                description=row.get("description") or "",
                model=row.get("model"),
                tools=list(row.get("tools_json") or []),
                system_prompt=row.get("system_prompt") or "",
                enabled=bool(row.get("enabled", True)),
            )
            for row in rows
        ]

    def _list_mcp_rows(self, agent_config_id: str) -> list[McpServerConfig]:
        rows = q.rows(self._table("agent_configs").select("mcp_json").eq("id", agent_config_id).execute(), _REPO, "_list_mcp_rows")
        if not rows:
            raise RuntimeError(f"Agent config {agent_config_id} disappeared while reading mcp_json")
        mcp_rows = rows[0].get("mcp_json") or []
        if not isinstance(mcp_rows, list):
            raise RuntimeError(f"Agent config {agent_config_id} mcp_json must be a JSON array")
        return [
            McpServerConfig(
                id=row.get("id"),
                name=row["name"],
                transport=row.get("transport"),
                command=row.get("command"),
                args=list(row.get("args") or []),
                env=dict(row.get("env") or {}),
                url=row.get("url"),
                instructions=row.get("instructions"),
                allowed_tools=row.get("allowed_tools"),
                enabled=bool(row.get("enabled", True)),
            )
            for row in mcp_rows
        ]
