"""Supabase repository for invite codes."""

from __future__ import annotations

import secrets
import string
from datetime import UTC, datetime, timedelta
from typing import Any

from storage.providers.supabase import _query as q

_REPO = "invite_code repo"
_TABLE = "invite_codes"


def _generate_code(length: int = 10) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _is_expired(row: dict) -> bool:
    expires_at = row.get("expires_at")
    if not expires_at:
        return False
    try:
        exp = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        return datetime.now(UTC) > exp
    except ValueError:
        return False


class SupabaseInviteCodeRepo:
    def __init__(self, client: Any) -> None:
        self._client = q.validate_client(client, _REPO)

    def close(self) -> None:
        return None

    def _table(self) -> Any:
        return self._client.table(_TABLE)

    def generate(
        self,
        *,
        created_by: str | None = None,
        expires_days: int | None = 7,
    ) -> dict[str, Any]:
        code = _generate_code()
        now = datetime.now(UTC).isoformat()
        expires_at = None
        if expires_days is not None:
            expires_at = (datetime.now(UTC) + timedelta(days=expires_days)).isoformat()
        self._table().insert(
            {
                "code": code,
                "created_by": created_by,
                "used_by": None,
                "used_at": None,
                "expires_at": expires_at,
                "created_at": now,
            }
        ).execute()
        return self.get(code) or {}

    def get(self, code: str) -> dict[str, Any] | None:
        rows = q.rows(
            self._table().select("*").eq("code", code).execute(),
            _REPO,
            "get",
        )
        return dict(rows[0]) if rows else None

    def list_all(self) -> list[dict[str, Any]]:
        rows = q.rows(
            q.order(self._table().select("*"), "created_at", desc=True, repo=_REPO, operation="list_all").execute(),
            _REPO,
            "list_all",
        )
        return [dict(r) for r in rows]

    def use(self, code: str, user_id: str) -> dict[str, Any] | None:
        """Atomically mark a code as used. Returns the row if successful, None if not valid."""
        now = datetime.now(UTC).isoformat()
        resp = (
            self._table()
            .update({"used_by": user_id, "used_at": now})
            .eq("code", code)
            .is_("used_by", None)  # atomic: only update if not already used
            .execute()
        )
        updated = resp.data or []
        if not updated:
            # Either code doesn't exist, already used, or expired — check which
            existing = self.get(code)
            if existing is None or existing.get("used_by") or _is_expired(existing):
                return None
            return None
        return dict(updated[0])

    def is_valid(self, code: str) -> bool:
        existing = self.get(code)
        if not existing:
            return False
        if existing.get("used_by"):
            return False
        return not _is_expired(existing)

    def revoke(self, code: str) -> bool:
        """Delete (revoke) a code. Returns True if it existed."""
        resp = self._table().delete().eq("code", code).execute()
        return bool(resp.data)
