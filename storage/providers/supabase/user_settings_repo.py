"""Supabase repository for per-user workspace preferences."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from json import JSONDecodeError
from typing import Any

from storage.providers.supabase import _query as q

_REPO = "user_settings repo"
_SCHEMA = "identity"
_TABLE = "user_settings"


class SupabaseUserSettingsRepo:
    def __init__(self, client: Any) -> None:
        self._client = q.validate_client(client, _REPO)

    def close(self) -> None:
        return None

    def _table(self) -> Any:
        return q.schema_table(self._client, _SCHEMA, _TABLE, _REPO)

    def get(self, user_id: str) -> dict[str, Any]:
        rows = q.rows(
            self._table().select("*").eq("user_id", user_id).execute(),
            _REPO,
            "get",
        )
        if not rows:
            return {"user_id": user_id, "default_workspace": None, "recent_workspaces": [], "default_model": "leon:large"}
        row = dict(rows[0])
        if isinstance(row.get("recent_workspaces"), str):
            try:
                row["recent_workspaces"] = json.loads(row["recent_workspaces"])
            except JSONDecodeError:
                row["recent_workspaces"] = []
        if row.get("recent_workspaces") is None:
            row["recent_workspaces"] = []
        return row

    def set_default_workspace(self, user_id: str, workspace: str) -> None:
        current = self.get(user_id)
        recents: list[str] = current.get("recent_workspaces") or []
        if workspace in recents:
            recents.remove(workspace)
        recents.insert(0, workspace)
        recents = recents[:5]
        self._upsert(user_id, {"default_workspace": workspace, "recent_workspaces": recents})

    def add_recent_workspace(self, user_id: str, workspace: str) -> None:
        current = self.get(user_id)
        recents: list[str] = current.get("recent_workspaces") or []
        if workspace in recents:
            recents.remove(workspace)
        recents.insert(0, workspace)
        recents = recents[:5]
        self._upsert(user_id, {"recent_workspaces": recents})

    def set_default_model(self, user_id: str, model: str) -> None:
        self._upsert(user_id, {"default_model": model})

    # ------------------------------------------------------------------
    # Models config (JSONB)
    # ------------------------------------------------------------------

    def get_models_config(self, user_id: str) -> dict[str, Any] | None:
        rows = q.rows(self._table().select("models_config").eq("user_id", user_id).execute(), _REPO, "get_models_config")
        if not rows:
            return None
        return rows[0].get("models_config")

    def set_models_config(self, user_id: str, config: dict[str, Any]) -> None:
        self._upsert(user_id, {"models_config": config})

    def get_account_resource_limits(self, user_id: str) -> dict[str, Any] | None:
        rows = q.rows(
            self._table().select("account_resource_limits").eq("user_id", user_id).execute(),
            _REPO,
            "get_account_resource_limits",
        )
        if not rows:
            return None
        return rows[0].get("account_resource_limits")

    def _upsert(self, user_id: str, updates: dict[str, Any]) -> None:
        now = datetime.now(UTC).isoformat()
        self._table().upsert({"user_id": user_id, "updated_at": now, **updates}).execute()
