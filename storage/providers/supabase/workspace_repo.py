"""Supabase repository for container workspaces."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from storage.contracts import WorkspaceRow
from storage.providers.supabase import _query as q

_REPO = "workspace repo"
_SCHEMA = "container"
_TABLE = "workspaces"
_COLS = (
    "id",
    "sandbox_id",
    "owner_user_id",
    "workspace_path",
    "name",
    "created_at",
    "updated_at",
)


def _to_timestamptz(value: float | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return datetime.fromtimestamp(value, UTC).isoformat()


def _to_row(row: dict[str, Any]) -> WorkspaceRow:
    return WorkspaceRow(
        id=str(row["id"]),
        sandbox_id=str(row["sandbox_id"]),
        owner_user_id=str(row["owner_user_id"]),
        workspace_path=str(row["workspace_path"]),
        name=row.get("name"),
        created_at=row["created_at"],
        updated_at=row.get("updated_at"),
    )


class SupabaseWorkspaceRepo:
    def __init__(self, client: Any) -> None:
        self._client = q.validate_client(client, _REPO)

    def close(self) -> None:
        return None

    def _t(self) -> Any:
        return q.schema_table(self._client, _SCHEMA, _TABLE, _REPO)

    def create(self, row: WorkspaceRow) -> None:
        created_at = _to_timestamptz(row.created_at)
        self._t().insert(
            {
                "id": row.id,
                "sandbox_id": row.sandbox_id,
                "owner_user_id": row.owner_user_id,
                "workspace_path": row.workspace_path,
                "name": row.name,
                "created_at": created_at,
                "updated_at": _to_timestamptz(row.updated_at) or created_at,
            }
        ).execute()

    def get_by_id(self, workspace_id: str) -> WorkspaceRow | None:
        response = self._t().select(", ".join(_COLS)).eq("id", workspace_id).execute()
        rows = q.rows(response, _REPO, "get_by_id")
        return _to_row(rows[0]) if rows else None

    def list_by_sandbox_id(self, sandbox_id: str) -> list[WorkspaceRow]:
        response = self._t().select(", ".join(_COLS)).eq("sandbox_id", sandbox_id).execute()
        return [_to_row(row) for row in q.rows(response, _REPO, "list_by_sandbox_id")]
