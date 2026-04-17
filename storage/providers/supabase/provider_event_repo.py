"""Supabase repository for sandbox provider webhook events."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from storage.providers.supabase import _query as q

_REPO = "provider event repo"
_TABLE = "provider_events"


class SupabaseProviderEventRepo:
    """Provider event persistence backed by Supabase (table: observability.provider_events)."""

    def __init__(self, client: Any) -> None:
        self._client = q.validate_client(client, _REPO)

    def close(self) -> None:
        return None

    def _t(self) -> Any:
        return q.schema_table(self._client, "observability", _TABLE, _REPO)

    def record(
        self,
        *,
        provider_name: str,
        instance_id: str,
        event_type: str,
        payload: dict[str, Any],
        matched_lease_id: str | None,
        matched_sandbox_id: str | None,
    ) -> None:
        self._t().insert(
            {
                "provider_name": provider_name,
                "instance_id": instance_id,
                "event_type": event_type,
                "payload_json": json.dumps(payload, ensure_ascii=False),
                "matched_lease_id": matched_lease_id,
                "matched_sandbox_id": matched_sandbox_id,
                "created_at": datetime.now().isoformat(),
            }
        ).execute()

    def list_recent(self, limit: int = 100) -> list[dict[str, Any]]:
        raw = q.rows(
            q.limit(
                q.order(
                    self._t().select(
                        "event_id,provider_name,instance_id,event_type,payload_json,matched_lease_id,matched_sandbox_id,created_at"
                    ),
                    "created_at",
                    desc=True,
                    repo=_REPO,
                    operation="list_recent",
                ),
                limit,
                _REPO,
                "list_recent",
            ).execute(),
            _REPO,
            "list_recent",
        )
        items: list[dict[str, Any]] = []
        for row in raw:
            item = dict(row)
            payload_raw = item.get("payload_json")
            item["payload"] = json.loads(payload_raw) if payload_raw else {}
            items.append(item)
        return items
