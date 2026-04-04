"""Supabase repositories for members and accounts."""

from __future__ import annotations

from typing import Any

from storage.contracts import AccountRow, MemberRow
from storage.providers.supabase import _query as q

_MEMBER_REPO = "member repo"
_MEMBER_TABLE = "members"

_ACCOUNT_REPO = "account repo"
_ACCOUNT_TABLE = "accounts"


class SupabaseMemberRepo:
    def __init__(self, client: Any) -> None:
        self._client = q.validate_client(client, _MEMBER_REPO)

    def close(self) -> None:
        return None

    def create(self, row: MemberRow) -> None:
        self._t().insert(
            {
                "id": row.id,
                "name": row.name,
                "type": row.type.value,
                "avatar": row.avatar,
                "description": row.description,
                "config_dir": row.config_dir,
                "owner_user_id": row.owner_user_id,
                "next_entity_seq": row.next_entity_seq,
                "email": row.email,
                "mycel_id": row.mycel_id,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }
        ).execute()

    def get_by_id(self, member_id: str) -> MemberRow | None:
        response = self._t().select("*").eq("id", member_id).execute()
        rows = q.rows(response, _MEMBER_REPO, "get_by_id")
        if not rows:
            return None
        return MemberRow.model_validate(self._normalize(rows[0]))

    def get_by_name(self, name: str) -> MemberRow | None:
        response = self._t().select("*").eq("name", name).execute()
        rows = q.rows(response, _MEMBER_REPO, "get_by_name")
        if not rows:
            return None
        return MemberRow.model_validate(self._normalize(rows[0]))

    def get_by_email(self, email: str) -> MemberRow | None:
        response = self._t().select("*").eq("email", email).execute()
        rows = q.rows(response, _MEMBER_REPO, "get_by_email")
        if not rows:
            return None
        return MemberRow.model_validate(self._normalize(rows[0]))

    def get_by_mycel_id(self, mycel_id: int) -> MemberRow | None:
        response = self._t().select("*").eq("mycel_id", mycel_id).execute()
        rows = q.rows(response, _MEMBER_REPO, "get_by_mycel_id")
        if not rows:
            return None
        return MemberRow.model_validate(self._normalize(rows[0]))

    def list_all(self) -> list[MemberRow]:
        query = q.order(self._t().select("*"), "created_at", desc=False, repo=_MEMBER_REPO, operation="list_all")
        rows = q.rows(query.execute(), _MEMBER_REPO, "list_all")
        return [MemberRow.model_validate(self._normalize(r)) for r in rows]

    def list_by_owner_user_id(self, owner_user_id: str) -> list[MemberRow]:
        query = q.order(
            self._t().select("*").eq("owner_user_id", owner_user_id),
            "created_at",
            desc=False,
            repo=_MEMBER_REPO,
            operation="list_by_owner_user_id",
        )
        rows = q.rows(query.execute(), _MEMBER_REPO, "list_by_owner_user_id")
        return [MemberRow.model_validate(self._normalize(r)) for r in rows]

    def update(self, member_id: str, **fields: Any) -> None:
        allowed = {"name", "avatar", "description", "config_dir", "owner_user_id", "updated_at"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return
        self._t().update(updates).eq("id", member_id).execute()

    def increment_entity_seq(self, member_id: str) -> int:
        """Atomically increment next_entity_seq and return the new value via RPC."""
        response = self._client.rpc(
            "increment_member_entity_seq",
            {"p_member_id": member_id},
        ).execute()
        # RPC returns scalar; supabase-py wraps it in data
        if isinstance(response, dict):
            data = response.get("data")
        else:
            data = getattr(response, "data", None)
        if data is None:
            raise RuntimeError(
                f"Supabase {_MEMBER_REPO} expected data from increment_member_entity_seq RPC. "
                "Check the function exists and member_id is valid."
            )
        # data may be a list with one element (scalar), or an int directly
        if isinstance(data, list):
            if not data:
                raise RuntimeError(f"Supabase {_MEMBER_REPO} increment_entity_seq returned empty list for member {member_id}.")
            return int(data[0])
        return int(data)

    def delete(self, member_id: str) -> None:
        self._t().delete().eq("id", member_id).execute()

    def _normalize(self, row: dict[str, Any]) -> dict[str, Any]:
        """Ensure type is a MemberType-compatible value."""
        return row

    def _t(self) -> Any:
        return self._client.table(_MEMBER_TABLE)


class SupabaseAccountRepo:
    def __init__(self, client: Any) -> None:
        self._client = q.validate_client(client, _ACCOUNT_REPO)

    def close(self) -> None:
        return None

    def create(self, row: AccountRow) -> None:
        self._t().insert(
            {
                "id": row.id,
                "user_id": row.user_id,
                "username": row.username,
                "password_hash": row.password_hash,
                "api_key_hash": row.api_key_hash,
                "created_at": row.created_at,
            }
        ).execute()

    def get_by_id(self, account_id: str) -> AccountRow | None:
        response = self._t().select("*").eq("id", account_id).execute()
        rows = q.rows(response, _ACCOUNT_REPO, "get_by_id")
        if not rows:
            return None
        return AccountRow.model_validate(rows[0])

    def get_by_user_id(self, user_id: str) -> AccountRow | None:
        response = self._t().select("*").eq("user_id", user_id).execute()
        rows = q.rows(response, _ACCOUNT_REPO, "get_by_user_id")
        if not rows:
            return None
        return AccountRow.model_validate(rows[0])

    def get_by_username(self, username: str) -> AccountRow | None:
        response = self._t().select("*").eq("username", username).execute()
        rows = q.rows(response, _ACCOUNT_REPO, "get_by_username")
        if not rows:
            return None
        return AccountRow.model_validate(rows[0])

    def delete(self, account_id: str) -> None:
        self._t().delete().eq("id", account_id).execute()

    def _t(self) -> Any:
        return self._client.table(_ACCOUNT_TABLE)
