"""Supabase repository for per-user/member new-thread config memory."""

from __future__ import annotations

import json
import time
from typing import Any

from storage.providers.supabase import _query as q
from storage.providers.supabase.schema import resolve_runtime_schema, route_for_schema

_REPO = "thread launch pref repo"
_TABLE = "thread_launch_prefs"
_AGENT_COLUMNS = {
    "public": "member_id",
    "staging": "agent_user_id",
}
_BASE_SELECT_COLUMNS = (
    "owner_user_id",
    "last_confirmed_json",
    "last_successful_json",
    "last_confirmed_at",
    "last_successful_at",
)


class SupabaseThreadLaunchPrefRepo:
    """Persist per-user/member last confirmed + successful new-thread config."""

    def __init__(self, client: Any, *, schema: str | None = None) -> None:
        self._client = q.validate_client(client, _REPO)
        self._schema = resolve_runtime_schema(schema)

    def close(self) -> None:
        return None

    def get(self, owner_user_id: str, member_id: str) -> dict[str, Any] | None:
        agent_column = self._agent_column
        select = ", ".join(("owner_user_id", agent_column, *_BASE_SELECT_COLUMNS[1:]))
        response = self._t().select(select).eq("owner_user_id", owner_user_id).eq(agent_column, member_id).execute()
        rows = q.rows(response, _REPO, "get")
        if not rows:
            return None
        row = rows[0]
        confirmed_raw = row.get("last_confirmed_json")
        successful_raw = row.get("last_successful_json")
        return {
            "owner_user_id": row["owner_user_id"],
            "member_id": row[agent_column],
            "last_confirmed": json.loads(confirmed_raw) if confirmed_raw else None,
            "last_successful": json.loads(successful_raw) if successful_raw else None,
            "last_confirmed_at": row.get("last_confirmed_at"),
            "last_successful_at": row.get("last_successful_at"),
        }

    def save_confirmed(self, owner_user_id: str, member_id: str, config: dict[str, Any]) -> None:
        self._save(owner_user_id, member_id, "last_confirmed_json", "last_confirmed_at", config)

    def save_successful(self, owner_user_id: str, member_id: str, config: dict[str, Any]) -> None:
        self._save(owner_user_id, member_id, "last_successful_json", "last_successful_at", config)

    def _save(
        self,
        owner_user_id: str,
        member_id: str,
        json_col: str,
        ts_col: str,
        config: dict[str, Any],
    ) -> None:
        payload = json.dumps(config, ensure_ascii=False)
        now = time.time()
        agent_column = self._agent_column
        # @@@thread-launch-pref-schema - application still says member_id; staging DB stores the same identity as agent_user_id.
        self._t().upsert(
            {
                "owner_user_id": owner_user_id,
                agent_column: member_id,
                json_col: payload,
                ts_col: now,
            },
            on_conflict=f"owner_user_id,{agent_column}",
        ).execute()

    def _t(self) -> Any:
        return self._client.table(_TABLE)

    @property
    def _agent_column(self) -> str:
        return route_for_schema(_REPO, _AGENT_COLUMNS, self._schema)
