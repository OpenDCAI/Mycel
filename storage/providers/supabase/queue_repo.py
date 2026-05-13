from __future__ import annotations

import json
from typing import Any

from storage.contracts import QueueItem
from storage.providers.supabase import _query as q

_REPO = "queue repo"
_TABLE = "message_queue"
_SENDER_USER_ID = "sender_user_id"


class SupabaseQueueRepo:
    def __init__(self, client: Any) -> None:
        self._client = q.validate_client(client, _REPO)

    def close(self) -> None:
        return None

    def _t(self) -> Any:
        return q.schema_table(self._client, "agent", _TABLE, _REPO)

    def _hydrate_metadata(self, row: dict[str, Any]) -> dict[str, Any] | None:
        raw = row.get("metadata_json")
        if raw is None:
            return None
        if isinstance(raw, dict):
            return dict(raw)
        if isinstance(raw, str):
            parsed = json.loads(raw)
            if not isinstance(parsed, dict):
                raise RuntimeError("Supabase queue repo expected metadata_json to decode to an object.")
            return parsed
        raise RuntimeError(f"Supabase queue repo expected metadata_json object or string, got {type(raw).__name__}.")

    def _hydrate_item(self, row: dict[str, Any]) -> QueueItem:
        return QueueItem(
            content=str(row.get("content") or ""),
            notification_type=row.get("notification_type") or "steer",
            source=row.get("source"),
            sender_id=row.get(_SENDER_USER_ID),
            sender_name=row.get("sender_name"),
            metadata=self._hydrate_metadata(row),
        )

    def enqueue(
        self,
        thread_id: str,
        content: str,
        notification_type: str = "steer",
        source: str | None = None,
        sender_id: str | None = None,
        sender_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._t().insert(
            {
                "thread_id": thread_id,
                "content": content,
                "notification_type": notification_type,
                "source": source,
                _SENDER_USER_ID: sender_id,
                "sender_name": sender_name,
                "metadata_json": dict(metadata or {}),
            }
        ).execute()

    def dequeue(self, thread_id: str) -> QueueItem | None:
        head = q.rows(
            q.limit(
                q.order(
                    self._t()
                    .select(f"id,content,notification_type,source,{_SENDER_USER_ID},sender_name,metadata_json")
                    .eq("thread_id", thread_id),
                    "id",
                    desc=False,
                    repo=_REPO,
                    operation="dequeue",
                ),
                1,
                _REPO,
                "dequeue",
            ).execute(),
            _REPO,
            "dequeue",
        )
        if not head:
            return None
        row = head[0]
        row_id = row.get("id")
        if row_id is None:
            raise RuntimeError("Supabase queue repo expected non-null id in dequeue row. Check message_queue table schema.")
        self._t().delete().eq("id", row_id).execute()
        return self._hydrate_item(row)

    def drain_all(self, thread_id: str) -> list[QueueItem]:
        # Fetch all rows ordered by id, then delete them all
        raw = q.rows(
            q.order(
                self._t()
                .select(f"id,content,notification_type,source,{_SENDER_USER_ID},sender_name,metadata_json")
                .eq("thread_id", thread_id),
                "id",
                desc=False,
                repo=_REPO,
                operation="drain_all",
            ).execute(),
            _REPO,
            "drain_all",
        )
        if not raw:
            return []
        self._t().delete().eq("thread_id", thread_id).execute()
        return [self._hydrate_item(r) for r in raw]

    def peek(self, thread_id: str) -> bool:
        rows = q.rows(
            q.limit(
                self._t().select("id").eq("thread_id", thread_id),
                1,
                _REPO,
                "peek",
            ).execute(),
            _REPO,
            "peek",
        )
        return len(rows) > 0

    def list_queue(self, thread_id: str) -> list[dict[str, Any]]:
        raw = q.rows(
            q.order(
                self._t().select("id,content,notification_type,created_at").eq("thread_id", thread_id),
                "id",
                desc=False,
                repo=_REPO,
                operation="list_queue",
            ).execute(),
            _REPO,
            "list_queue",
        )
        return [
            {
                "id": r.get("id"),
                "content": r.get("content"),
                "notification_type": r.get("notification_type"),
                "created_at": r.get("created_at"),
            }
            for r in raw
        ]

    def clear_queue(self, thread_id: str) -> None:
        self._t().delete().eq("thread_id", thread_id).execute()

    def count(self, thread_id: str) -> int:
        raw = q.rows(
            self._t().select("id").eq("thread_id", thread_id).execute(),
            _REPO,
            "count",
        )
        return len(raw)
