"""Supabase repository for AgentConfig aggregates."""

from __future__ import annotations

from typing import Any

from config.agent_config_types import AgentConfig, AgentRule, AgentSkill, AgentSubAgent, McpServerConfig
from storage.providers.supabase import _query as q

_REPO = "agent_config repo"
_SCHEMA = "agent"
_LIBRARY_SCHEMA = "library"


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


def _enabled_from_row(row: dict[str, Any], *, label: str) -> bool:
    enabled = row.get("enabled", True)
    if not isinstance(enabled, bool):
        raise RuntimeError(f"{label} enabled must be a boolean")
    return enabled


def _json_array(value: Any, *, label: str, default: list[Any] | None = None) -> list[Any]:
    if value is None:
        return list(default or [])
    if not isinstance(value, list):
        raise RuntimeError(f"{label} must be a JSON array")
    return list(value)


def _required_json_array(value: Any, *, label: str) -> list[Any]:
    if value is None:
        raise RuntimeError(f"{label} must be a JSON array")
    return _json_array(value, label=label)


def _json_object(value: Any, *, label: str, default: dict[str, Any] | None = None) -> dict[str, Any]:
    if value is None:
        return dict(default or {})
    if not isinstance(value, dict):
        raise RuntimeError(f"{label} must be a JSON object")
    return dict(value)


def _required_json_object(value: Any, *, label: str) -> dict[str, Any]:
    if value is None:
        raise RuntimeError(f"{label} must be a JSON object")
    return _json_object(value, label=label)


class SupabaseAgentConfigRepo:
    def __init__(self, client: Any) -> None:
        self._client = q.validate_client(client, _REPO)

    def close(self) -> None:
        return None

    def _table(self, table: str) -> Any:
        return q.schema_table(self._client, _SCHEMA, table, _REPO)

    def _library_table(self, table: str) -> Any:
        return q.schema_table(self._client, _LIBRARY_SCHEMA, table, _REPO)

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
            tools=_required_json_array(root.get("tools_json"), label="tools_json"),
            system_prompt=root.get("system_prompt") or "",
            status=root.get("status") or "draft",
            version=root.get("version") or "0.1.0",
            runtime_settings=_required_json_object(root.get("runtime_json"), label="runtime_json"),
            compact=_required_json_object(root.get("compact_json"), label="compact_json"),
            meta=_required_json_object(root.get("meta_json"), label="meta_json"),
            skills=self._list_skill_rows(agent_config_id, root["owner_user_id"]),
            rules=self._list_rule_rows(agent_config_id),
            sub_agents=self._list_sub_agent_rows(agent_config_id),
            mcp_servers=self._list_mcp_rows(agent_config_id),
        )

    def save_agent_config(self, config: AgentConfig) -> None:
        _reject_duplicate_child_names(config)
        payload = config.model_dump(mode="json")
        q.schema_rpc(self._client, _SCHEMA, "save_agent_config", {"payload": payload}, _REPO).execute()

    def delete_agent_config(self, agent_config_id: str) -> None:
        self._table("skill_bindings").delete().eq("agent_config_id", agent_config_id).execute()
        self._table("agent_rules").delete().eq("agent_config_id", agent_config_id).execute()
        self._table("agent_sub_agents").delete().eq("agent_config_id", agent_config_id).execute()
        self._table("agent_configs").delete().eq("id", agent_config_id).execute()

    def _list_skill_rows(self, agent_config_id: str, owner_user_id: str) -> list[AgentSkill]:
        binding_rows = q.rows(
            self._table("skill_bindings").select("*").eq("agent_config_id", agent_config_id).execute(),
            _REPO,
            "_list_skill_rows",
        )
        skills: list[AgentSkill] = []
        for row in binding_rows:
            skill_id = row["skill_id"]
            package_id = row["package_id"]
            skill = self._get_library_skill(owner_user_id, skill_id)
            package = self._get_skill_package(owner_user_id, package_id)
            skills.append(
                AgentSkill(
                    id=row.get("id"),
                    skill_id=skill_id,
                    package_id=package_id,
                    name=skill["name"],
                    description=skill.get("description") or "",
                    version=package["version"],
                    enabled=_enabled_from_row(row, label="skill_bindings"),
                    source=_required_json_object(package.get("source_json"), label="skill package source_json"),
                )
            )
        return skills

    def _get_library_skill(self, owner_user_id: str, skill_id: str) -> dict[str, Any]:
        rows = q.rows(
            self._library_table("skills").select("*").eq("owner_user_id", owner_user_id).eq("id", skill_id).execute(),
            _REPO,
            "_get_library_skill",
        )
        if not rows:
            raise RuntimeError(f"AgentConfig references missing Library skill: {skill_id}")
        return dict(rows[0])

    def _get_skill_package(self, owner_user_id: str, package_id: str) -> dict[str, Any]:
        rows = q.rows(
            self._library_table("skill_packages").select("*").eq("owner_user_id", owner_user_id).eq("id", package_id).execute(),
            _REPO,
            "_get_skill_package",
        )
        if not rows:
            raise RuntimeError(f"AgentConfig references missing Skill package: {package_id}")
        return dict(rows[0])

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
                enabled=_enabled_from_row(row, label="agent_rules"),
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
                tools=_json_array(row.get("tools_json"), label="agent_sub_agents tools_json"),
                system_prompt=row.get("system_prompt") or "",
                enabled=_enabled_from_row(row, label="agent_sub_agents"),
            )
            for row in rows
        ]

    def _list_mcp_rows(self, agent_config_id: str) -> list[McpServerConfig]:
        rows = q.rows(self._table("agent_configs").select("mcp_json").eq("id", agent_config_id).execute(), _REPO, "_list_mcp_rows")
        if not rows:
            raise RuntimeError(f"Agent config {agent_config_id} disappeared while reading mcp_json")
        mcp_rows = _required_json_array(rows[0].get("mcp_json"), label=f"Agent config {agent_config_id} mcp_json")
        servers: list[McpServerConfig] = []
        for row in mcp_rows:
            if not isinstance(row, dict):
                raise RuntimeError(f"Agent config {agent_config_id} mcp_json items must be JSON objects")
            if "disabled" in row:
                raise RuntimeError(f"Agent config {agent_config_id} mcp_json items must use enabled")
            servers.append(
                McpServerConfig(
                    id=row.get("id"),
                    name=row["name"],
                    transport=row.get("transport"),
                    command=row.get("command"),
                    args=_json_array(row.get("args"), label="mcp_json item args"),
                    env=_json_object(row.get("env"), label="mcp_json item env"),
                    url=row.get("url"),
                    instructions=row.get("instructions"),
                    allowed_tools=row.get("allowed_tools"),
                    enabled=_enabled_from_row(row, label=f"Agent config {agent_config_id} mcp_json item"),
                )
            )
        return servers
