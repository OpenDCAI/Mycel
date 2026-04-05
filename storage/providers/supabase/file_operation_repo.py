"""Supabase repository for file operation persistence operations."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from storage.models import FileOperationRow
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
        response = self._t().insert(
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
        ).execute()
        inserted = q.rows(response, _REPO, "record")
        if not inserted:
            raise RuntimeError(
                "Supabase file operation repo expected inserted row for record. "
                "Check table permissions."
            )
        inserted_id = inserted[0].get("id")
        if not inserted_id:
            raise RuntimeError(
                "Supabase file operation repo expected non-null id in record response. "
                "Check file_operations table schema."
            )
        return str(inserted_id)

    def get_operations_for_thread(self, thread_id: str, status: str = "applied") -> list[FileOperationRow]:
        query = q.order(
            self._t().select("*").eq("thread_id", thread_id).eq("status", status),
            "timestamp", desc=False, repo=_REPO, operation="get_operations_for_thread",
        )
        return [self._hydrate(row, "get_operations_for_thread") for row in q.rows(query.execute(), _REPO, "get_operations_for_thread")]

    def get_operations_after_checkpoint(self, thread_id: str, checkpoint_id: str) -> list[FileOperationRow]:
        ts_rows = q.rows(
            q.limit(
                q.order(
                    self._t().select("timestamp").eq("thread_id", thread_id).eq("checkpoint_id", checkpoint_id),
                    "timestamp", desc=False, repo=_REPO, operation="get_operations_after_checkpoint ts",
                ),
                1, _REPO, "get_operations_after_checkpoint ts",
            ).execute(),
            _REPO, "get_operations_after_checkpoint ts",
        )

        if not ts_rows:
            query = q.order(
                self._t().select("*").eq("thread_id", thread_id).eq("status", "applied"),
                "timestamp", desc=True, repo=_REPO, operation="get_operations_after_checkpoint",
            )
        else:
            target_ts = ts_rows[0].get("timestamp")
            if target_ts is None:
                raise RuntimeError(
                    "Supabase file operation repo expected non-null timestamp in checkpoint ts lookup. "
                    "Check file_operations table schema."
                )
            query = q.order(
                q.gte(
                    self._t().select("*").eq("thread_id", thread_id).eq("status", "applied"),
                    "timestamp", target_ts, _REPO, "get_operations_after_checkpoint",
                ),
                "timestamp", desc=True, repo=_REPO, operation="get_operations_after_checkpoint",
            )
        return [self._hydrate(row, "get_operations_after_checkpoint") for row in q.rows(query.execute(), _REPO, "get_operations_after_checkpoint")]

    def get_operations_between_checkpoints(
        self,
        thread_id: str,
        from_checkpoint_id: str,
        to_checkpoint_id: str,
    ) -> list[FileOperationRow]:
        # @@@checkpoint-window-parity - mirror SQLite WHERE checkpoint_id != from_checkpoint_id at query level.
        query = q.order(
            self._t().select("*")
                .eq("thread_id", thread_id)
                .neq("checkpoint_id", from_checkpoint_id)
                .eq("status", "applied"),
            "timestamp", desc=True, repo=_REPO, operation="get_operations_between_checkpoints",
        )
        all_rows = q.rows(query.execute(), _REPO, "get_operations_between_checkpoints")

        result: list[FileOperationRow] = []
        for row in all_rows:
            if row.get("checkpoint_id") == to_checkpoint_id:
                break
            result.append(self._hydrate(row, "get_operations_between_checkpoints"))
        return result

    def get_operations_for_checkpoint(self, thread_id: str, checkpoint_id: str) -> list[FileOperationRow]:
        query = q.order(
            self._t().select("*").eq("thread_id", thread_id).eq("checkpoint_id", checkpoint_id).eq("status", "applied"),
            "timestamp", desc=False, repo=_REPO, operation="get_operations_for_checkpoint",
        )
        return [self._hydrate(row, "get_operations_for_checkpoint") for row in q.rows(query.execute(), _REPO, "get_operations_for_checkpoint")]

    def count_operations_for_checkpoint(self, thread_id: str, checkpoint_id: str) -> int:
        query = self._t().select("id").eq("thread_id", thread_id).eq("checkpoint_id", checkpoint_id).eq("status", "applied")
        return len(q.rows(query.execute(), _REPO, "count_operations_for_checkpoint"))

    def mark_reverted(self, operation_ids: list[str]) -> None:
        if not operation_ids:
            return
        q.in_(self._t().update({"status": "reverted"}), "id", operation_ids, _REPO, "mark_reverted").execute()

    def delete_thread_operations(self, thread_id: str) -> int:
        pre = q.rows(self._t().select("id").eq("thread_id", thread_id).execute(), _REPO, "delete_thread_operations")
        self._t().delete().eq("thread_id", thread_id).execute()
        return len(pre)

    def _t(self) -> Any:
        return self._client.table(_TABLE)

    def _hydrate(self, row: dict[str, Any], operation: str) -> FileOperationRow:
        required = ("id", "thread_id", "checkpoint_id", "timestamp", "operation_type", "file_path", "after_content", "status")
        missing = [f for f in required if row.get(f) is None]
        if missing:
            raise RuntimeError(
                f"Supabase file operation repo expected non-null {', '.join(missing)} in {operation} row. "
                "Check file_operations table schema."
            )

        before_content = row.get("before_content")
        if before_content is not None and not isinstance(before_content, str):
            raise RuntimeError(
                f"Supabase file operation repo expected before_content to be str or null in {operation}, "
                f"got {type(before_content).__name__}."
            )

        changes_raw = row.get("changes")
        if changes_raw in (None, ""):
            changes: list[dict[str, Any]] | None = None
        elif isinstance(changes_raw, str):
            try:
                loaded = json.loads(changes_raw)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"Supabase file operation repo expected valid JSON in changes column ({operation}): {exc}."
                ) from exc
            if not isinstance(loaded, list) or not all(isinstance(i, dict) for i in loaded):
                raise RuntimeError(
                    f"Supabase file operation repo expected changes JSON to decode to list[dict] in {operation}."
                )
            changes = loaded
        elif isinstance(changes_raw, list):
            if not all(isinstance(i, dict) for i in changes_raw):
                raise RuntimeError(
                    f"Supabase file operation repo expected changes list items to be dict in {operation}."
                )
            changes = changes_raw
        else:
            raise RuntimeError(
                f"Supabase file operation repo expected changes to be list, JSON string, or null in {operation}, "
                f"got {type(changes_raw).__name__}."
            )

        return FileOperationRow(
            id=str(row["id"]),
            thread_id=str(row["thread_id"]),
            checkpoint_id=str(row["checkpoint_id"]),
            timestamp=float(row["timestamp"]),
            operation_type=str(row["operation_type"]),
            file_path=str(row["file_path"]),
            before_content=before_content,
            after_content=str(row["after_content"]),
            changes=changes,
            status=str(row["status"]),
        )
