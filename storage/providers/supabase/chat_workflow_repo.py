from __future__ import annotations

import time
from typing import Any

from core.work_item.types import WorkItem
from storage.contracts import ChatWorkflowRow
from storage.providers.supabase import _query as q

_SCHEMA = "chat"
_WORKFLOW_REPO = "chat workflow repo"
_TASK_REPO = "chat task repo"


class SupabaseChatWorkflowRepo:
    def __init__(self, client: Any) -> None:
        self._client = q.validate_client(client, _WORKFLOW_REPO)

    def close(self) -> None:
        return None

    def get(self, chat_id: str) -> ChatWorkflowRow | None:
        rows = q.rows(self._t().select("*").eq("chat_id", chat_id).limit(1).execute(), _WORKFLOW_REPO, "get")
        return _row_to_workflow(rows[0]) if rows else None

    def upsert(
        self,
        chat_id: str,
        *,
        kind: str,
        state: str = "active",
        config: dict[str, Any] | None = None,
        updated_by_user_id: str | None = None,
    ) -> ChatWorkflowRow:
        now = time.time()
        existing = self.get(chat_id)
        payload = {
            "chat_id": chat_id,
            "kind": kind,
            "state": state,
            "config_json": config or {},
            "updated_by_user_id": updated_by_user_id,
            "created_at": existing.created_at if existing else now,
            "updated_at": now,
        }
        rows = q.rows(
            self._t().upsert(payload, on_conflict="chat_id").execute(),
            _WORKFLOW_REPO,
            "upsert",
        )
        return _row_to_workflow(rows[0] if rows else payload)

    def delete(self, chat_id: str) -> None:
        self._t().delete().eq("chat_id", chat_id).execute()

    def _t(self) -> Any:
        return q.schema_table(self._client, _SCHEMA, "workflow_state", _WORKFLOW_REPO)


class SupabaseChatTaskRepo:
    def __init__(self, client: Any) -> None:
        self._client = q.validate_client(client, _TASK_REPO)

    def close(self) -> None:
        return None

    def next_id(self, scope_id: str) -> str:
        rows = q.rows(self._t().select("task_id").eq("chat_id", scope_id).execute(), _TASK_REPO, "next_id")
        if not rows:
            return "1"
        return str(max(int(str(row["task_id"])) for row in rows) + 1)

    def get(self, scope_id: str, item_id: str) -> WorkItem | None:
        rows = q.rows(
            self._t().select("*").eq("chat_id", scope_id).eq("task_id", item_id).limit(1).execute(),
            _TASK_REPO,
            "get",
        )
        return _row_to_work_item(rows[0]) if rows else None

    def list_all(self, scope_id: str) -> list[WorkItem]:
        rows = q.rows(
            q.order(
                self._t().select("*").eq("chat_id", scope_id),
                "task_id",
                desc=False,
                repo=_TASK_REPO,
                operation="list_all",
            ).execute(),
            _TASK_REPO,
            "list_all",
        )
        return [_row_to_work_item(row) for row in rows]

    def insert(self, scope_id: str, item: WorkItem) -> None:
        self._t().insert(_work_item_payload(scope_id, item)).execute()

    def update(self, scope_id: str, item: WorkItem) -> None:
        payload = _work_item_payload(scope_id, item)
        payload.pop("created_at", None)
        self._t().update(payload).eq("chat_id", scope_id).eq("task_id", item.id).execute()

    def delete(self, scope_id: str, item_id: str) -> None:
        self._t().delete().eq("chat_id", scope_id).eq("task_id", item_id).execute()

    def _t(self) -> Any:
        return q.schema_table(self._client, _SCHEMA, "tasks", _TASK_REPO)


def _row_to_workflow(row: dict[str, Any]) -> ChatWorkflowRow:
    return ChatWorkflowRow(
        chat_id=str(row["chat_id"]),
        kind=str(row["kind"]),
        state=str(row.get("state") or "active"),
        config=dict(row.get("config_json") or row.get("config") or {}),
        updated_by_user_id=row.get("updated_by_user_id"),
        created_at=float(row["created_at"]),
        updated_at=float(row["updated_at"]) if row.get("updated_at") is not None else None,
    )


def _row_to_work_item(row: dict[str, Any]) -> WorkItem:
    return WorkItem(
        id=str(row["task_id"]),
        subject=str(row.get("subject") or ""),
        description=str(row.get("description") or ""),
        status=str(row.get("status") or "pending"),
        active_form=row.get("active_form"),
        owner=row.get("owner_user_id") or row.get("owner"),
        blocks=list(row.get("blocks_json") or row.get("blocks") or []),
        blocked_by=list(row.get("blocked_by_json") or row.get("blocked_by") or []),
        metadata=dict(row.get("metadata_json") or row.get("metadata") or {}),
    )


def _work_item_payload(scope_id: str, item: WorkItem) -> dict[str, Any]:
    now = time.time()
    status = item.status.value if hasattr(item.status, "value") else str(item.status)
    return {
        "chat_id": scope_id,
        "task_id": item.id,
        "subject": item.subject,
        "description": item.description,
        "status": status,
        "active_form": item.active_form,
        "owner_user_id": item.owner,
        "blocks_json": list(item.blocks),
        "blocked_by_json": list(item.blocked_by),
        "metadata_json": dict(item.metadata),
        "created_at": now,
        "updated_at": now,
    }
