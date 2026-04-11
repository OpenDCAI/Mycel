"""Supabase repository for unified users."""

from __future__ import annotations

from typing import Any

from storage.contracts import UserRow
from storage.providers.supabase import _query as q

_USER_REPO = "user repo"
_USER_TABLE = "users"
_COLS = (
    "id",
    "type",
    "display_name",
    "owner_user_id",
    "agent_config_id",
    "next_thread_seq",
    "avatar",
    "email",
    "mycel_id",
    "created_at",
    "updated_at",
)


class SupabaseUserRepo:
    def __init__(self, client: Any) -> None:
        self._client = q.validate_client(client, _USER_REPO)

    def close(self) -> None:
        return None

    def create(self, row: UserRow) -> None:
        self._t().insert(
            {
                "id": row.id,
                "type": row.type.value,
                "display_name": row.display_name,
                "owner_user_id": row.owner_user_id,
                "agent_config_id": row.agent_config_id,
                "next_thread_seq": row.next_thread_seq,
                "avatar": row.avatar,
                "email": row.email,
                "mycel_id": row.mycel_id,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }
        ).execute()

    def get_by_id(self, user_id: str) -> UserRow | None:
        return self._get_single("get_by_id", id=user_id)

    def get_by_email(self, email: str) -> UserRow | None:
        return self._get_single("get_by_email", email=email)

    def get_by_mycel_id(self, mycel_id: int) -> UserRow | None:
        return self._get_single("get_by_mycel_id", mycel_id=mycel_id)

    def list_by_ids(self, user_ids: list[str]) -> list[UserRow]:
        if not user_ids:
            return []
        rows = q.rows_in_chunks(lambda: self._t().select(", ".join(_COLS)), "id", user_ids, _USER_REPO, "list_by_ids")
        users_by_id = {row["id"]: UserRow.model_validate(row) for row in rows}
        return [users_by_id[user_id] for user_id in user_ids if user_id in users_by_id]

    def list_all(self) -> list[UserRow]:
        query = q.order(self._t().select(", ".join(_COLS)), "created_at", desc=False, repo=_USER_REPO, operation="list_all")
        rows = q.rows(query.execute(), _USER_REPO, "list_all")
        return [UserRow.model_validate(row) for row in rows]

    def list_by_type(self, user_type: str) -> list[UserRow]:
        query = q.order(
            self._t().select(", ".join(_COLS)).eq("type", user_type),
            "created_at",
            desc=False,
            repo=_USER_REPO,
            operation="list_by_type",
        )
        rows = q.rows(query.execute(), _USER_REPO, "list_by_type")
        return [UserRow.model_validate(row) for row in rows]

    def list_by_owner_user_id(self, owner_user_id: str) -> list[UserRow]:
        query = q.order(
            self._t().select(", ".join(_COLS)).eq("owner_user_id", owner_user_id),
            "created_at",
            desc=False,
            repo=_USER_REPO,
            operation="list_by_owner_user_id",
        )
        rows = q.rows(query.execute(), _USER_REPO, "list_by_owner_user_id")
        return [UserRow.model_validate(row) for row in rows]

    def update(self, user_id: str, **fields: Any) -> None:
        allowed = {"display_name", "owner_user_id", "agent_config_id", "avatar", "email", "mycel_id", "updated_at"}
        updates = {key: value for key, value in fields.items() if key in allowed}
        if not updates:
            return
        self._t().update(updates).eq("id", user_id).execute()

    def increment_thread_seq(self, user_id: str) -> int:
        response = self._client.rpc("increment_user_thread_seq", {"p_user_id": user_id}).execute()
        if isinstance(response, dict):
            data = response.get("data")
        else:
            data = getattr(response, "data", None)
        if data is None:
            raise RuntimeError(
                f"Supabase {_USER_REPO} expected data from increment_user_thread_seq RPC. Check the function exists and user_id is valid."
            )
        if isinstance(data, list):
            if not data:
                raise RuntimeError(f"Supabase {_USER_REPO} increment_thread_seq returned empty list for user {user_id}.")
            return int(data[0])
        return int(data)

    def delete(self, user_id: str) -> None:
        self._t().delete().eq("id", user_id).execute()

    def _get_single(self, operation: str, **eq_filters: Any) -> UserRow | None:
        query = self._t().select(", ".join(_COLS))
        for key, value in eq_filters.items():
            query = query.eq(key, value)
        rows = q.rows(query.execute(), _USER_REPO, operation)
        if not rows:
            return None
        return UserRow.model_validate(rows[0])

    def _t(self) -> Any:
        return self._client.table(_USER_TABLE)
