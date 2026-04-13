"""Supabase repository for threads."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from storage.providers.supabase import _query as q
from storage.providers.supabase.schema import resolve_runtime_schema

_REPO = "thread repo"
_SCHEMA = "agent"
_TABLE = "threads"
_THREAD_MEMBER_COLUMN = "agent_user_id"
_BASE_COLS = (
    "id",
    "sandbox_type",
    "model",
    "cwd",
    "is_main",
    "branch_index",
    "created_at",
)


def _validate_thread_identity(*, is_main: bool, branch_index: int) -> None:
    if branch_index < 0:
        raise ValueError(f"branch_index must be >= 0, got {branch_index}")
    if is_main and branch_index != 0:
        raise ValueError(f"Main thread must have branch_index=0, got {branch_index}")
    if not is_main and branch_index == 0:
        raise ValueError("Child thread must have branch_index>0")


def _select_cols(schema: str) -> tuple[str, ...]:
    resolve_runtime_schema(schema)
    return (_THREAD_MEMBER_COLUMN, *_BASE_COLS)


def _to_dict(row: dict[str, Any], schema: str) -> dict[str, Any]:
    result = {c: row.get(c) for c in _BASE_COLS}
    resolve_runtime_schema(schema)
    result["member_id"] = row.get(_THREAD_MEMBER_COLUMN)
    result["observation_provider"] = row.get("observation_provider")
    result["is_main"] = bool(result["is_main"])
    result["branch_index"] = int(result["branch_index"]) if result["branch_index"] is not None else 0
    return result


def _created_at_payload(schema: str, created_at: float) -> float | str:
    resolve_runtime_schema(schema)
    return datetime.fromtimestamp(created_at, tz=UTC).isoformat()


def _is_main_payload(schema: str, is_main: bool) -> bool | int:
    resolve_runtime_schema(schema)
    return is_main


class SupabaseThreadRepo:
    def __init__(self, client: Any, *, schema: str | None = None) -> None:
        self._client = q.validate_client(client, _REPO)
        self._schema = resolve_runtime_schema(schema)

    def close(self) -> None:
        return None

    def create(
        self,
        thread_id: str,
        member_id: str,
        sandbox_type: str,
        cwd: str | None = None,
        created_at: float = 0,
        **extra: Any,
    ) -> None:
        is_main = bool(extra.get("is_main", False))
        branch_index = int(extra["branch_index"])
        _validate_thread_identity(is_main=is_main, branch_index=branch_index)
        owner_user_id = extra.get("owner_user_id")
        if not owner_user_id:
            raise ValueError("owner_user_id is required when creating agent.threads rows")
        payload = {
            "id": thread_id,
            self._thread_member_column: member_id,
            "owner_user_id": owner_user_id,
            "sandbox_type": sandbox_type,
            "cwd": cwd,
            "model": extra.get("model"),
            "is_main": _is_main_payload(self._schema, is_main),
            "branch_index": branch_index,
            "created_at": _created_at_payload(self._schema, created_at),
        }
        self._t().insert(payload).execute()

    def get_by_id(self, thread_id: str) -> dict[str, Any] | None:
        select = ", ".join(_select_cols(self._schema))
        response = self._t().select(select).eq("id", thread_id).execute()
        rows = q.rows(response, _REPO, "get_by_id")
        if not rows:
            return None
        return _to_dict(rows[0], self._schema)

    def get_main_thread(self, member_id: str) -> dict[str, Any] | None:
        select = ", ".join(_select_cols(self._schema))
        response = (
            self._t().select(select).eq(self._thread_member_column, member_id).eq("is_main", _is_main_payload(self._schema, True)).execute()
        )
        rows = q.rows(response, _REPO, "get_main_thread")
        if not rows:
            return None
        return _to_dict(rows[0], self._schema)

    def get_next_branch_index(self, member_id: str) -> int:
        response = self._t().select("branch_index").eq(self._thread_member_column, member_id).execute()
        rows = q.rows(response, _REPO, "get_next_branch_index")
        if not rows:
            return 1
        max_idx = max((int(r["branch_index"]) for r in rows if r.get("branch_index") is not None), default=0)
        return max_idx + 1

    def list_by_member(self, member_id: str) -> list[dict[str, Any]]:
        select = ", ".join(_select_cols(self._schema))
        query = q.order(
            q.order(
                self._t().select(select).eq(self._thread_member_column, member_id),
                "branch_index",
                desc=False,
                repo=_REPO,
                operation="list_by_member",
            ),
            "created_at",
            desc=False,
            repo=_REPO,
            operation="list_by_member",
        )
        rows = q.rows(query.execute(), _REPO, "list_by_member")
        return [_to_dict(r, self._schema) for r in rows]

    def list_by_owner_user_id(self, owner_user_id: str) -> list[dict[str, Any]]:
        """Return all threads owned by this user via a two-step query (members JOIN threads).

        Thread rows already carry owner_user_id in the migrated agent schema.
        """
        thread_cols = ", ".join(_select_cols(self._schema))
        query = q.order(
            q.order(
                self._t().select(thread_cols).eq("owner_user_id", owner_user_id),
                "is_main",
                desc=True,
                repo=_REPO,
                operation="list_by_owner_user_id",
            ),
            "created_at",
            desc=False,
            repo=_REPO,
            operation="list_by_owner_user_id",
        )
        thread_rows = q.rows(query.execute(), _REPO, "list_by_owner_user_id:agent_threads")

        result: list[dict[str, Any]] = []
        for raw in thread_rows:
            d = _to_dict(raw, self._schema)
            d["member_name"] = None
            d["member_avatar"] = None
            d["entity_name"] = None
            result.append(d)
        return result

    def update(self, thread_id: str, **fields: Any) -> None:
        allowed = {"sandbox_type", "model", "cwd", "is_main", "branch_index"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return
        next_is_main = bool(updates["is_main"]) if "is_main" in updates else None
        next_branch_index = int(updates["branch_index"]) if "branch_index" in updates else None
        if next_is_main is not None or next_branch_index is not None:
            current = self.get_by_id(thread_id)
            if current is None:
                raise ValueError(f"Thread {thread_id} not found")
            _validate_thread_identity(
                is_main=next_is_main if next_is_main is not None else bool(current["is_main"]),
                branch_index=next_branch_index if next_branch_index is not None else int(current["branch_index"]),
            )
        if "is_main" in updates:
            updates["is_main"] = _is_main_payload(self._schema, bool(updates["is_main"]))
        self._t().update(updates).eq("id", thread_id).execute()

    def delete(self, thread_id: str) -> None:
        self._t().delete().eq("id", thread_id).execute()

    def _t(self) -> Any:
        return self._client.schema(_SCHEMA).table(_TABLE)

    @property
    def _thread_member_column(self) -> str:
        resolve_runtime_schema(self._schema)
        return _THREAD_MEMBER_COLUMN
