"""Supabase repository for threads."""

from __future__ import annotations

from typing import Any

from storage.providers.supabase import _query as q

_REPO = "thread repo"
_TABLE = "threads"

_COLS = (
    "id",
    "agent_user_id",
    "sandbox_type",
    "model",
    "cwd",
    "status",
    "is_main",
    "branch_index",
    "created_at",
    "updated_at",
    "last_active_at",
)


def _validate_thread_identity(*, is_main: bool, branch_index: int) -> None:
    if branch_index < 0:
        raise ValueError(f"branch_index must be >= 0, got {branch_index}")
    if is_main and branch_index != 0:
        raise ValueError(f"Default thread must have branch_index=0, got {branch_index}")
    if not is_main and branch_index == 0:
        raise ValueError("Child thread must have branch_index>0")


def _to_dict(row: dict[str, Any]) -> dict[str, Any]:
    result = {c: row.get(c) for c in _COLS}
    result["is_main"] = bool(result["is_main"])
    result["branch_index"] = int(result["branch_index"]) if result["branch_index"] is not None else 0
    return result


class SupabaseThreadRepo:
    def __init__(self, client: Any) -> None:
        self._client = q.validate_client(client, _REPO)

    def close(self) -> None:
        return None

    def create(
        self,
        thread_id: str,
        agent_user_id: str,
        sandbox_type: str,
        cwd: str | None = None,
        created_at: float = 0,
        *,
        model: str | None = None,
        is_main: bool,
        branch_index: int,
        status: str = "active",
        updated_at: float | None = None,
        last_active_at: float | None = None,
    ) -> None:
        _validate_thread_identity(is_main=is_main, branch_index=branch_index)
        self._t().insert(
            {
                "id": thread_id,
                "agent_user_id": agent_user_id,
                "sandbox_type": sandbox_type,
                "cwd": cwd,
                "model": model,
                "status": status,
                "is_main": int(is_main),
                "branch_index": branch_index,
                "created_at": created_at,
                "updated_at": updated_at,
                "last_active_at": last_active_at,
            }
        ).execute()

    def get_by_id(self, thread_id: str) -> dict[str, Any] | None:
        select = ", ".join(_COLS)
        response = self._t().select(select).eq("id", thread_id).execute()
        rows = q.rows(response, _REPO, "get_by_id")
        if not rows:
            return None
        return _to_dict(rows[0])

    def list_by_ids(self, thread_ids: list[str]) -> list[dict[str, Any]]:
        ordered_ids: list[str] = []
        seen: set[str] = set()
        for thread_id in thread_ids:
            normalized = str(thread_id or "").strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            ordered_ids.append(normalized)
        if not ordered_ids:
            return []
        select = ", ".join(_COLS)
        rows = q.rows_in_chunks(lambda: self._t().select(select), "id", ordered_ids, _REPO, "list_by_ids")
        normalized_rows = [_to_dict(row) for row in rows]
        indexed = {row["id"]: row for row in normalized_rows}
        return [indexed[thread_id] for thread_id in ordered_ids if thread_id in indexed]

    def get_by_user_id(self, user_id: str) -> dict[str, Any] | None:
        select = ", ".join(_COLS)
        # @@@agent-user-thread-lookup - social/user-facing lookups must resolve to the
        # representative main thread, not an arbitrary branch, once one agent can own
        # multiple thread rows.
        response = self._t().select(select).eq("agent_user_id", user_id).eq("is_main", 1).execute()
        rows = q.rows(response, _REPO, "get_by_user_id")
        if not rows:
            return None
        return _to_dict(rows[0])

    def get_default_thread(self, agent_user_id: str) -> dict[str, Any] | None:
        select = ", ".join(_COLS)
        response = self._t().select(select).eq("agent_user_id", agent_user_id).eq("is_main", 1).execute()
        rows = q.rows(response, _REPO, "get_default_thread")
        if not rows:
            return None
        return _to_dict(rows[0])

    def list_default_threads(self, agent_user_ids: list[str]) -> dict[str, dict[str, Any]]:
        ordered_ids: list[str] = []
        seen: set[str] = set()
        for agent_user_id in agent_user_ids:
            normalized = str(agent_user_id or "").strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            ordered_ids.append(normalized)
        if not ordered_ids:
            return {}
        select = ", ".join(_COLS)
        rows = q.rows_in_chunks(
            lambda: self._t().select(select).eq("is_main", 1),
            "agent_user_id",
            ordered_ids,
            _REPO,
            "list_default_threads",
        )
        return {str(row["agent_user_id"]): _to_dict(row) for row in rows}

    def get_next_branch_index(self, agent_user_id: str) -> int:
        response = self._t().select("branch_index").eq("agent_user_id", agent_user_id).execute()
        rows = q.rows(response, _REPO, "get_next_branch_index")
        if not rows:
            return 1
        max_idx = max((int(r["branch_index"]) for r in rows if r.get("branch_index") is not None), default=0)
        return max_idx + 1

    def list_by_agent_user(self, agent_user_id: str) -> list[dict[str, Any]]:
        select = ", ".join(_COLS)
        query = q.order(
            q.order(
                self._t().select(select).eq("agent_user_id", agent_user_id),
                "branch_index",
                desc=False,
                repo=_REPO,
                operation="list_by_agent_user",
            ),
            "created_at",
            desc=False,
            repo=_REPO,
            operation="list_by_agent_user",
        )
        rows = q.rows(query.execute(), _REPO, "list_by_agent_user")
        return [_to_dict(r) for r in rows]

    def list_by_owner_user_id(self, owner_user_id: str) -> list[dict[str, Any]]:
        """Return all threads owned by this user via a two-step query (users JOIN threads)."""
        user_response = self._client.table("users").select("id, display_name, avatar").eq("owner_user_id", owner_user_id).execute()
        user_rows = q.rows(user_response, _REPO, "list_by_owner_user_id:users")
        if not user_rows:
            return []

        user_map: dict[str, dict[str, Any]] = {r["id"]: r for r in user_rows}
        agent_user_ids = list(user_map.keys())

        # Step 2: get threads for those agent users
        thread_cols = ", ".join(_COLS)
        thread_rows = q.rows_in_chunks(
            lambda: q.order(
                q.order(
                    self._t().select(thread_cols),
                    "is_main",
                    desc=True,
                    repo=_REPO,
                    operation="list_by_owner_user_id",
                ),
                "created_at",
                desc=False,
                repo=_REPO,
                operation="list_by_owner_user_id",
            ),
            "agent_user_id",
            agent_user_ids,
            _REPO,
            "list_by_owner_user_id:threads",
        )

        # Step 3: enrich with agent display data from user_map
        result: list[dict[str, Any]] = []
        for raw in thread_rows:
            d = _to_dict(raw)
            agent_user_id = d["agent_user_id"]
            agent_info = user_map.get(agent_user_id, {})
            d["agent_name"] = agent_info.get("display_name")
            d["agent_avatar"] = agent_info.get("avatar")
            result.append(d)
        return result

    def update(self, thread_id: str, **fields: Any) -> None:
        allowed = {"sandbox_type", "model", "cwd", "status", "is_main", "branch_index", "updated_at", "last_active_at"}
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
            updates["is_main"] = int(bool(updates["is_main"]))
        self._t().update(updates).eq("id", thread_id).execute()

    def delete(self, thread_id: str) -> None:
        self._t().delete().eq("id", thread_id).execute()

    def _t(self) -> Any:
        return self._client.table(_TABLE)
