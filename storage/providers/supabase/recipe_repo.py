"""Supabase repository for user-scoped recipe overrides and custom recipes."""

from __future__ import annotations

import json
import time
from typing import Any

from storage.providers.supabase import _query as q

_REPO = "recipe repo"
_TABLE = "library_recipes"


class SupabaseRecipeRepo:
    def __init__(self, client: Any) -> None:
        self._client = q.validate_client(client, _REPO)

    def close(self) -> None:
        return None

    def list_by_owner(self, owner_user_id: str) -> list[dict[str, Any]]:
        query = q.order(
            q.order(
                self._t()
                .select("owner_user_id, recipe_id, kind, provider_type, data_json, created_at, updated_at")
                .eq("owner_user_id", owner_user_id),
                "created_at",
                desc=False,
                repo=_REPO,
                operation="list_by_owner",
            ),
            "recipe_id",
            desc=False,
            repo=_REPO,
            operation="list_by_owner",
        )
        rows = q.rows(query.execute(), _REPO, "list_by_owner")
        return [self._hydrate(r) for r in rows]

    def get(self, owner_user_id: str, recipe_id: str) -> dict[str, Any] | None:
        response = (
            self._t()
            .select("owner_user_id, recipe_id, kind, provider_type, data_json, created_at, updated_at")
            .eq("owner_user_id", owner_user_id)
            .eq("recipe_id", recipe_id)
            .execute()
        )
        rows = q.rows(response, _REPO, "get")
        if not rows:
            return None
        return self._hydrate(rows[0])

    def upsert(
        self,
        *,
        owner_user_id: str,
        recipe_id: str,
        kind: str,
        provider_type: str,
        data: dict[str, Any],
        created_at: int | None = None,
    ) -> dict[str, Any]:
        if kind not in {"custom", "override"}:
            raise ValueError(f"Unsupported recipe row kind: {kind}")
        now = int(time.time() * 1000)
        existing = self.get(owner_user_id, recipe_id)
        created = int(created_at if created_at is not None else existing["created_at"] if existing else now)
        payload = json.dumps(data, ensure_ascii=False)
        self._t().upsert(
            {
                "owner_user_id": owner_user_id,
                "recipe_id": recipe_id,
                "kind": kind,
                "provider_type": provider_type,
                "data_json": payload,
                "created_at": created,
                "updated_at": now,
            },
            on_conflict="owner_user_id,recipe_id",
        ).execute()
        row = self.get(owner_user_id, recipe_id)
        if row is None:
            raise RuntimeError("recipe upsert failed")
        return row

    def delete(self, owner_user_id: str, recipe_id: str) -> bool:
        # Pre-check existence so we can return bool without rowcount
        existing = self.get(owner_user_id, recipe_id)
        if existing is None:
            return False
        self._t().delete().eq("owner_user_id", owner_user_id).eq("recipe_id", recipe_id).execute()
        return True

    def delete_thread_events(self, thread_id: str) -> int:
        # RecipeRepo protocol requires this for parity; recipes are not keyed by thread_id,
        # so this is a no-op that returns 0.
        return 0

    def _hydrate(self, row: dict[str, Any]) -> dict[str, Any]:
        raw = row.get("data_json") or row.get("data") or "{}"
        if isinstance(raw, dict):
            payload = raw
        else:
            payload = json.loads(str(raw))
        if not isinstance(payload, dict):
            raise ValueError("recipe payload must be an object")
        return {
            "owner_user_id": str(row["owner_user_id"]),
            "recipe_id": str(row["recipe_id"]),
            "kind": str(row["kind"]),
            "provider_type": str(row["provider_type"]),
            "data": payload,
            "created_at": int(row["created_at"]),
            "updated_at": int(row["updated_at"]),
        }

    def _t(self) -> Any:
        return self._client.table(_TABLE)
