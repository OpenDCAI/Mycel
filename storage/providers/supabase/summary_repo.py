"""Supabase repository for summaries persistence operations."""

from __future__ import annotations

from typing import Any

from storage.providers.supabase import _query as q

_REPO = "summary repo"
_TABLE = "summaries"


class SupabaseSummaryRepo:
    """Minimal summary repository backed by a Supabase client."""

    def __init__(self, client: Any) -> None:
        self._client = q.validate_client(client, _REPO)

    def close(self) -> None:
        return None

    def ensure_tables(self) -> None:
        """Supabase schema is managed via migrations, not runtime DDL."""
        return None

    def save_summary(
        self,
        summary_id: str,
        thread_id: str,
        summary_text: str,
        compact_up_to_index: int,
        compacted_at: int,
        is_split_turn: bool,
        split_turn_prefix: str | None,
        created_at: str,
    ) -> None:
        self._t().update({"is_active": False}).eq("thread_id", thread_id).eq("is_active", True).execute()
        response = self._t().insert(
            {
                "summary_id": summary_id,
                "thread_id": thread_id,
                "summary_text": summary_text,
                "compact_up_to_index": compact_up_to_index,
                "compacted_at": compacted_at,
                "is_split_turn": is_split_turn,
                "split_turn_prefix": split_turn_prefix,
                "is_active": True,
                "created_at": created_at,
            }
        ).execute()
        inserted = q.rows(response, _REPO, "save_summary")
        if not inserted:
            raise RuntimeError(
                "Supabase summary repo expected inserted row for save_summary. "
                "Check table permissions."
            )
        if inserted[0].get("summary_id") is None:
            raise RuntimeError(
                "Supabase summary repo expected non-null summary_id in save_summary response. "
                "Check summaries table schema."
            )

    def get_latest_summary_row(self, thread_id: str) -> dict[str, Any] | None:
        query = q.limit(
            q.order(
                self._t().select(
                    "summary_id,thread_id,summary_text,compact_up_to_index,compacted_at,"
                    "is_split_turn,split_turn_prefix,is_active,created_at"
                ).eq("thread_id", thread_id).eq("is_active", True),
                "created_at", desc=True, repo=_REPO, operation="get_latest_summary_row",
            ),
            1, _REPO, "get_latest_summary_row",
        )
        rows = q.rows(query.execute(), _REPO, "get_latest_summary_row")
        if not rows:
            return None
        return self._hydrate_full(rows[0], "get_latest_summary_row")

    def list_summaries(self, thread_id: str) -> list[dict[str, object]]:
        query = q.order(
            self._t().select(
                "summary_id,thread_id,compact_up_to_index,compacted_at,is_split_turn,is_active,created_at"
            ).eq("thread_id", thread_id),
            "created_at", desc=True, repo=_REPO, operation="list_summaries",
        )
        return [self._hydrate_listing(row, "list_summaries") for row in q.rows(query.execute(), _REPO, "list_summaries")]

    def delete_thread_summaries(self, thread_id: str) -> None:
        self._t().delete().eq("thread_id", thread_id).execute()

    def _t(self) -> Any:
        return self._client.table(_TABLE)

    def _required(self, row: dict[str, Any], field: str, operation: str) -> Any:
        value = row.get(field)
        if value is None:
            raise RuntimeError(
                f"Supabase summary repo expected non-null {field} in {operation} row. "
                "Check summaries table schema."
            )
        return value

    def _as_bool(self, value: Any, field: str, operation: str) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, int) and value in (0, 1):
            return bool(value)
        raise RuntimeError(
            f"Supabase summary repo expected {field} to be bool (or 0/1 int) in {operation}, "
            f"got {type(value).__name__}."
        )

    def _hydrate_full(self, row: dict[str, Any], operation: str) -> dict[str, Any]:
        # @@@bool-normalization - avoid silent truthiness bugs like bool("false") == True.
        return {
            "summary_id": str(self._required(row, "summary_id", operation)),
            "thread_id": str(self._required(row, "thread_id", operation)),
            "summary_text": str(self._required(row, "summary_text", operation)),
            "compact_up_to_index": int(self._required(row, "compact_up_to_index", operation)),
            "compacted_at": int(self._required(row, "compacted_at", operation)),
            "is_split_turn": self._as_bool(self._required(row, "is_split_turn", operation), "is_split_turn", operation),
            "split_turn_prefix": str(row["split_turn_prefix"]) if row.get("split_turn_prefix") is not None else None,
            "is_active": self._as_bool(self._required(row, "is_active", operation), "is_active", operation),
            "created_at": str(self._required(row, "created_at", operation)),
        }

    def _hydrate_listing(self, row: dict[str, Any], operation: str) -> dict[str, object]:
        return {
            "summary_id": str(self._required(row, "summary_id", operation)),
            "thread_id": str(self._required(row, "thread_id", operation)),
            "compact_up_to_index": int(self._required(row, "compact_up_to_index", operation)),
            "compacted_at": int(self._required(row, "compacted_at", operation)),
            "is_split_turn": self._as_bool(self._required(row, "is_split_turn", operation), "is_split_turn", operation),
            "is_active": self._as_bool(self._required(row, "is_active", operation), "is_active", operation),
            "created_at": str(self._required(row, "created_at", operation)),
        }
