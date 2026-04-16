"""Supabase repository for agent registry persistence."""

from __future__ import annotations

from typing import Any

from storage.providers.supabase import _query as q

_REPO = "agent_registry repo"
_TABLE = "agent_registry"


class SupabaseAgentRegistryRepo:
    def __init__(self, client: Any) -> None:
        self._client = q.validate_client(client, _REPO)

    def close(self) -> None:
        return None

    def _table(self) -> Any:
        return self._client.table(_TABLE)

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
        self._table().upsert(
            {
                "agent_id": agent_id,
                "name": name,
                "thread_id": thread_id,
                "status": status,
                "parent_agent_id": parent_agent_id,
                "subagent_type": subagent_type,
            }
        ).execute()

    def list_running_by_name(self, name: str) -> list[tuple]:
        rows = q.rows(
            self._table()
            .select("agent_id,name,thread_id,status,parent_agent_id,subagent_type")
            .eq("name", name)
            .eq("status", "running")
            .execute(),
            _REPO,
            "list_running_by_name",
        )
        return [(r["agent_id"], r["name"], r["thread_id"], r["status"], r.get("parent_agent_id"), r.get("subagent_type")) for r in rows]

    def remove(self, agent_id: str) -> None:
        self._table().delete().eq("agent_id", agent_id).execute()
