"""Supabase repository for container sandboxes."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from storage.contracts import SandboxRow
from storage.providers.supabase import _query as q

_REPO = "sandbox repo"
_SCHEMA = "container"
_TABLE = "sandboxes"
_COLS = (
    "id",
    "owner_user_id",
    "provider_name",
    "provider_env_id",
    "sandbox_template_id",
    "desired_state",
    "observed_state",
    "status",
    "observed_at",
    "last_error",
    "config",
    "created_at",
    "updated_at",
)


def _to_timestamptz(value: float | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return datetime.fromtimestamp(value, UTC).isoformat()


def _to_row(row: dict[str, Any]) -> SandboxRow:
    return SandboxRow(
        id=str(row["id"]),
        owner_user_id=str(row["owner_user_id"]),
        provider_name=str(row["provider_name"]),
        provider_env_id=row.get("provider_env_id"),
        sandbox_template_id=row.get("sandbox_template_id"),
        desired_state=str(row["desired_state"]),
        observed_state=str(row["observed_state"]),
        status=str(row["status"]),
        observed_at=row["observed_at"],
        last_error=row.get("last_error"),
        config=row.get("config") or {},
        created_at=row["created_at"],
        updated_at=row.get("updated_at"),
    )


class SupabaseSandboxRepo:
    def __init__(self, client: Any) -> None:
        self._client = q.validate_client(client, _REPO)

    def close(self) -> None:
        return None

    def _t(self) -> Any:
        return q.schema_table(self._client, _SCHEMA, _TABLE, _REPO)

    def create(self, row: SandboxRow) -> None:
        created_at = _to_timestamptz(row.created_at)
        self._t().insert(
            {
                "id": row.id,
                "owner_user_id": row.owner_user_id,
                "provider_name": row.provider_name,
                "provider_env_id": row.provider_env_id,
                "sandbox_template_id": row.sandbox_template_id,
                "desired_state": row.desired_state,
                "observed_state": row.observed_state,
                "status": row.status,
                "observed_at": _to_timestamptz(row.observed_at),
                "last_error": row.last_error,
                "config": row.config,
                "created_at": created_at,
                "updated_at": _to_timestamptz(row.updated_at) or created_at,
            }
        ).execute()

    def update_runtime_binding(self, *, sandbox_id: str, provider_env_id: str | None, updated_at: float | str) -> None:
        self._t().update(
            {
                "provider_env_id": provider_env_id,
                "updated_at": _to_timestamptz(updated_at),
            }
        ).eq("id", sandbox_id).execute()

    def get_by_id(self, sandbox_id: str) -> SandboxRow | None:
        response = self._t().select(", ".join(_COLS)).eq("id", sandbox_id).execute()
        rows = q.rows(response, _REPO, "get_by_id")
        return _to_row(rows[0]) if rows else None
