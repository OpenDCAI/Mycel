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
    # agent_configs (1:1 with member)
    # ------------------------------------------------------------------

    def get_config(self, member_id: str) -> dict[str, Any] | None:
        rows = q.rows(
            self._client.table("agent_configs").select("*").eq("member_id", member_id).execute(),
            _REPO,
            "get_config",
        )
        return dict(rows[0]) if rows else None

    def save_config(self, member_id: str, data: dict[str, Any]) -> None:
        payload = {"member_id": member_id, **{k: v for k, v in data.items() if k != "member_id"}}
        self._client.table("agent_configs").upsert(payload).execute()

    def delete_config(self, member_id: str) -> None:
        self._client.table("agent_configs").delete().eq("member_id", member_id).execute()

    # ------------------------------------------------------------------
    # agent_rules
    # ------------------------------------------------------------------

    def list_rules(self, member_id: str) -> list[dict[str, Any]]:
        rows = q.rows(
            self._client.table("agent_rules").select("*").eq("member_id", member_id).execute(),
            _REPO,
            "list_rules",
        )
        return [dict(r) for r in rows]

    def save_rule(self, member_id: str, filename: str, content: str, rule_id: str | None = None) -> dict[str, Any]:
        rid = rule_id or str(uuid.uuid4())
        payload = {"id": rid, "member_id": member_id, "filename": filename, "content": content}
        self._client.table("agent_rules").upsert(payload).execute()
        return payload

    def delete_rule(self, rule_id: str) -> None:
        self._client.table("agent_rules").delete().eq("id", rule_id).execute()

    # ------------------------------------------------------------------
    # agent_skills
    # ------------------------------------------------------------------

    def list_skills(self, member_id: str) -> list[dict[str, Any]]:
        rows = q.rows(
            self._client.table("agent_skills").select("*").eq("member_id", member_id).execute(),
            _REPO,
            "list_skills",
        )
        return [dict(r) for r in rows]

    def save_skill(self, member_id: str, name: str, content: str, meta: dict | None = None, skill_id: str | None = None) -> dict[str, Any]:
        sid = skill_id or str(uuid.uuid4())
        payload: dict[str, Any] = {"id": sid, "member_id": member_id, "name": name, "content": content}
        if meta:
            payload["meta"] = meta
        self._client.table("agent_skills").upsert(payload, on_conflict="member_id,name").execute()
        return payload

    def delete_skill(self, skill_id: str) -> None:
        self._client.table("agent_skills").delete().eq("id", skill_id).execute()

    # ------------------------------------------------------------------
    # agent_sub_agents
    # ------------------------------------------------------------------

    def list_sub_agents(self, member_id: str) -> list[dict[str, Any]]:
        rows = q.rows(
            self._client.table("agent_sub_agents").select("*").eq("member_id", member_id).execute(),
            _REPO,
            "list_sub_agents",
        )
        return [dict(r) for r in rows]

    def save_sub_agent(
        self,
        member_id: str,
        name: str,
        *,
        description: str | None = None,
        model: str | None = None,
        tools: list | None = None,
        system_prompt: str | None = None,
        sub_agent_id: str | None = None,
    ) -> dict[str, Any]:
        sid = sub_agent_id or str(uuid.uuid4())
        payload: dict[str, Any] = {"id": sid, "member_id": member_id, "name": name}
        if description is not None:
            payload["description"] = description
        if model is not None:
            payload["model"] = model
        if tools is not None:
            payload["tools"] = tools
        if system_prompt is not None:
            payload["system_prompt"] = system_prompt
        self._client.table("agent_sub_agents").upsert(payload, on_conflict="member_id,name").execute()
        return payload

    def delete_sub_agent(self, sub_agent_id: str) -> None:
        self._client.table("agent_sub_agents").delete().eq("id", sub_agent_id).execute()
