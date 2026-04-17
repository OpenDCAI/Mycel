"""Supabase repository for file operation persistence operations."""

from __future__ import annotations

import time
import uuid
from typing import Any

from storage.providers.supabase import _query as q

_REPO = "file operation repo"
_TABLE = "file_operations"


class SupabaseFileOperationRepo:
    """Minimal file operation repository backed by a Supabase client."""

    def __init__(self, client: Any) -> None:
        self._client = q.validate_client(client, _REPO)

    def close(self) -> None:
        return None

    def record(
        self,
        thread_id: str,
        checkpoint_id: str,
        operation_type: str,
        file_path: str,
        before_content: str | None,
        after_content: str,
        changes: list[dict] | None = None,
    ) -> str:
        op_id = str(uuid.uuid4())
        response = (
            self._t()
            .insert(
                {
                    "id": op_id,
                    "thread_id": thread_id,
                    "checkpoint_id": checkpoint_id,
                    "timestamp": time.time(),
                    "operation_type": operation_type,
                    "file_path": file_path,
                    "before_content": before_content,
                    "after_content": after_content,
                    "changes": changes,
                    "status": "applied",
                }
            )
            .execute()
        )
        inserted = q.rows(response, _REPO, "record")
        if not inserted:
            raise RuntimeError("Supabase file operation repo expected inserted row for record. Check table permissions.")
        inserted_id = inserted[0].get("id")
        if not inserted_id:
            raise RuntimeError("Supabase file operation repo expected non-null id in record response. Check file_operations table schema.")
        return str(inserted_id)

    def delete_thread_operations(self, thread_id: str) -> int:
        pre = q.rows(self._t().select("id").eq("thread_id", thread_id).execute(), _REPO, "delete_thread_operations")
        self._t().delete().eq("thread_id", thread_id).execute()
        return len(pre)

    def _t(self) -> Any:
        return q.schema_table(self._client, "agent", _TABLE, _REPO)
