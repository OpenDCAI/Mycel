"""Supabase repository for monitor operation persistence."""

from __future__ import annotations

import json
from typing import Any

from storage.providers.supabase import _query as q

_REPO = "monitor operation repo"
_TABLE = "monitor_operations"
_SCHEMA = "observability"


def _raise_if_operation_schema_drift(err: Exception) -> None:
    message = str(err)
    if f"{_SCHEMA}.{_TABLE}" not in message or "schema cache" not in message:
        return
    raise RuntimeError("observability.monitor_operations is missing; refresh the Supabase schema cache before retrying") from err


class SupabaseMonitorOperationRepo:
    def __init__(self, client: Any) -> None:
        self._client = q.validate_client(client, _REPO)

    def close(self) -> None:
        return None

    def create(self, operation: dict[str, Any]) -> dict[str, Any]:
        try:
            rows = q.rows(self._t().upsert(self._row_from_operation(operation), on_conflict="operation_id").execute(), _REPO, "create")
        except Exception as err:
            _raise_if_operation_schema_drift(err)
            raise
        if not rows:
            raise RuntimeError(
                "Supabase monitor operation repo expected inserted row for create. Check monitor_operations table permissions."
            )
        return self._operation_from_row(rows[0], operation="create")

    def save(self, operation: dict[str, Any]) -> None:
        try:
            self._t().upsert(self._row_from_operation(operation), on_conflict="operation_id").execute()
        except Exception as err:
            _raise_if_operation_schema_drift(err)
            raise

    def list_for_target(self, target_type: str, target_id: str) -> list[dict[str, Any]]:
        try:
            rows = q.rows(
                q.order(
                    self._t().select("*").eq("target_type", target_type).eq("target_id", target_id),
                    "requested_at",
                    desc=True,
                    repo=_REPO,
                    operation="list_for_target",
                ).execute(),
                _REPO,
                "list_for_target",
            )
        except Exception as err:
            _raise_if_operation_schema_drift(err)
            raise
        return [self._operation_from_row(row, operation="list_for_target") for row in rows]

    def get(self, operation_id: str) -> dict[str, Any] | None:
        try:
            rows = q.rows(self._t().select("*").eq("operation_id", operation_id).execute(), _REPO, "get")
        except Exception as err:
            _raise_if_operation_schema_drift(err)
            raise
        if not rows:
            return None
        return self._operation_from_row(rows[0], operation="get")

    def clear(self) -> int:
        try:
            rows = q.rows(self._t().delete().neq("operation_id", "").execute(), _REPO, "clear")
        except Exception as err:
            _raise_if_operation_schema_drift(err)
            raise
        return len(rows)

    def _t(self) -> Any:
        return q.schema_table(self._client, _SCHEMA, _TABLE, _REPO)

    def _row_from_operation(self, operation: dict[str, Any]) -> dict[str, Any]:
        return {
            "operation_id": str(operation["operation_id"]),
            "kind": str(operation["kind"]),
            "target_type": str(operation["target_type"]),
            "target_id": str(operation["target_id"]),
            "status": str(operation["status"]),
            "requested_at": str(operation["requested_at"]),
            "updated_at": str(operation["updated_at"]),
            "payload_json": json.dumps(operation, ensure_ascii=False),
        }

    def _operation_from_row(self, row: dict[str, Any], *, operation: str) -> dict[str, Any]:
        payload_raw = row.get("payload_json")
        if not isinstance(payload_raw, str) or not payload_raw:
            raise RuntimeError(
                f"Supabase monitor operation repo expected non-empty payload_json in {operation}. "
                "Check observability.monitor_operations table schema."
            )
        payload = json.loads(payload_raw)
        if not isinstance(payload, dict):
            raise RuntimeError(
                f"Supabase monitor operation repo expected payload_json object in {operation}. "
                "Check observability.monitor_operations table schema."
            )
        return payload
