"""Supabase repository for agent configuration (config, rules, skills, sub-agents)."""

from __future__ import annotations

import uuid
from typing import Any

from storage.providers.supabase import _query as q

_REPO = "agent_config repo"


class SupabaseAgentConfigRepo:
    def __init__(self, client: Any) -> None:
        self._client = q.validate_client(client, _REPO)

    def close(self) -> None:
        return None

    # ------------------------------------------------------------------
    # agent_configs (1:1 with agent_config id)
    # ------------------------------------------------------------------

    def get_config(self, agent_config_id: str) -> dict[str, Any] | None:
        rows = q.rows(
            self._client.table("agent_configs").select("*").eq("id", agent_config_id).execute(),
            _REPO,
            "get_config",
        )
        if not rows:
            return None
        row = dict(rows[0])
        meta = row.get("meta_json") or {}
        if not isinstance(meta, dict):
            raise RuntimeError(f"Supabase {_REPO} expected meta_json object for get_config.")
        meta = dict(meta)
        compact = meta.pop("compact", None)
        result = {
            **row,
            "tools": row.get("tools_json", []),
            "runtime": row.get("runtime_json", {}),
            "mcp": row.get("mcp_json", {}),
            "meta": meta,
        }
        if compact is not None:
            result["compact"] = compact
        return result

    def save_config(self, agent_config_id: str, data: dict[str, Any]) -> None:
        payload = {"id": agent_config_id, **{k: v for k, v in data.items() if k != "id"}}
        if "tools" in payload:
            payload["tools_json"] = payload.pop("tools")
        if "runtime" in payload:
            payload["runtime_json"] = payload.pop("runtime")
        if "mcp" in payload:
            payload["mcp_json"] = payload.pop("mcp")
        meta = payload.pop("meta", {})
        if meta is None:
            meta = {}
        if not isinstance(meta, dict):
            raise RuntimeError(f"Supabase {_REPO} expected meta object for save_config.")
        meta = dict(meta)
        if "compact" in payload:
            compact = payload.pop("compact")
            if compact is None:
                meta.pop("compact", None)
            else:
                meta["compact"] = compact
        payload["meta_json"] = meta
        self._client.table("agent_configs").upsert(payload).execute()

    def delete_config(self, agent_config_id: str) -> None:
        self._client.table("agent_configs").delete().eq("id", agent_config_id).execute()

    # ------------------------------------------------------------------
    # agent_rules
    # ------------------------------------------------------------------

    def list_rules(self, agent_config_id: str) -> list[dict[str, Any]]:
        rows = q.rows(
            self._client.table("agent_rules").select("*").eq("agent_config_id", agent_config_id).execute(),
            _REPO,
            "list_rules",
        )
        return [dict(r) for r in rows]

    def save_rule(self, agent_config_id: str, filename: str, content: str, rule_id: str | None = None) -> dict[str, Any]:
        rid = rule_id or str(uuid.uuid4())
        payload = {"id": rid, "agent_config_id": agent_config_id, "filename": filename, "content": content}
        self._client.table("agent_rules").upsert(payload).execute()
        return payload

    def delete_rule(self, rule_id: str) -> None:
        self._client.table("agent_rules").delete().eq("id", rule_id).execute()

    # ------------------------------------------------------------------
    # agent_skills
    # ------------------------------------------------------------------

    def list_skills(self, agent_config_id: str) -> list[dict[str, Any]]:
        rows = q.rows(
            self._client.table("agent_skills").select("*").eq("agent_config_id", agent_config_id).execute(),
            _REPO,
            "list_skills",
        )
        return [dict(r) for r in rows]

    def save_skill(
        self, agent_config_id: str, name: str, content: str, meta: dict | None = None, skill_id: str | None = None
    ) -> dict[str, Any]:
        sid = skill_id or str(uuid.uuid4())
        payload: dict[str, Any] = {"id": sid, "agent_config_id": agent_config_id, "name": name, "content": content}
        if meta:
            payload["meta_json"] = meta
        self._client.table("agent_skills").upsert(payload, on_conflict="agent_config_id,name").execute()
        return payload

    def delete_skill(self, skill_id: str) -> None:
        self._client.table("agent_skills").delete().eq("id", skill_id).execute()

    # ------------------------------------------------------------------
    # agent_sub_agents
    # ------------------------------------------------------------------

    def list_sub_agents(self, agent_config_id: str) -> list[dict[str, Any]]:
        rows = q.rows(
            self._client.table("agent_sub_agents").select("*").eq("agent_config_id", agent_config_id).execute(),
            _REPO,
            "list_sub_agents",
        )
        return [dict(r) for r in rows]

    def save_sub_agent(
        self,
        agent_config_id: str,
        name: str,
        *,
        description: str | None = None,
        model: str | None = None,
        tools: list | None = None,
        system_prompt: str | None = None,
        sub_agent_id: str | None = None,
    ) -> dict[str, Any]:
        sid = sub_agent_id or str(uuid.uuid4())
        payload: dict[str, Any] = {"id": sid, "agent_config_id": agent_config_id, "name": name}
        if description is not None:
            payload["description"] = description
        if model is not None:
            payload["model"] = model
        if tools is not None:
            payload["tools_json"] = tools
        if system_prompt is not None:
            payload["system_prompt"] = system_prompt
        self._client.table("agent_sub_agents").upsert(payload, on_conflict="agent_config_id,name").execute()
        return payload

    def delete_sub_agent(self, sub_agent_id: str) -> None:
        self._client.table("agent_sub_agents").delete().eq("id", sub_agent_id).execute()
