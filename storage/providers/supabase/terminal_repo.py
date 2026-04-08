"""Supabase repository for abstract terminal persistence."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from storage.providers.supabase import _query as q

_REPO = "terminal repo"
_TERMINALS_TABLE = "abstract_terminals"
_POINTERS_TABLE = "thread_terminal_pointers"


class SupabaseTerminalRepo:
    """Abstract terminal CRUD backed by Supabase.

    Returns raw dicts — domain object construction is the consumer's job.
    """

    def __init__(self, client: Any) -> None:
        self._client = q.validate_client(client, _REPO)

    def close(self) -> None:
        return None

    def _terminals(self) -> Any:
        return self._client.table(_TERMINALS_TABLE)

    def _pointers(self) -> Any:
        return self._client.table(_POINTERS_TABLE)

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def _get_pointer_row(self, thread_id: str) -> dict[str, Any] | None:
        rows = q.rows(
            self._pointers().select("thread_id,active_terminal_id,default_terminal_id").eq("thread_id", thread_id).execute(),
            _REPO,
            "get_pointer",
        )
        return dict(rows[0]) if rows else None

    def get_active(self, thread_id: str) -> dict[str, Any] | None:
        pointer = self._get_pointer_row(thread_id)
        if pointer is None:
            return None
        return self.get_by_id(str(pointer["active_terminal_id"]))

    def get_default(self, thread_id: str) -> dict[str, Any] | None:
        pointer = self._get_pointer_row(thread_id)
        if pointer is None:
            return None
        return self.get_by_id(str(pointer["default_terminal_id"]))

    def get_by_id(self, terminal_id: str) -> dict[str, Any] | None:
        rows = q.rows(
            self._terminals()
            .select("terminal_id,thread_id,lease_id,cwd,env_delta_json,state_version,created_at,updated_at")
            .eq("terminal_id", terminal_id)
            .execute(),
            _REPO,
            "get_by_id",
        )
        return dict(rows[0]) if rows else None

    def get_latest_by_lease(self, lease_id: str) -> dict[str, Any] | None:
        rows = q.rows(
            q.limit(
                q.order(
                    self._terminals()
                    .select("terminal_id,thread_id,lease_id,cwd,env_delta_json,state_version,created_at,updated_at")
                    .eq("lease_id", lease_id),
                    "created_at",
                    desc=True,
                    repo=_REPO,
                    operation="get_latest_by_lease",
                ),
                1,
                _REPO,
                "get_latest_by_lease",
            ).execute(),
            _REPO,
            "get_latest_by_lease",
        )
        return dict(rows[0]) if rows else None

    def get_timestamps(self, terminal_id: str) -> tuple[str | None, str | None]:
        row = self.get_by_id(terminal_id)
        if row is None:
            return None, None
        return str(row.get("created_at") or "") or None, str(row.get("updated_at") or "") or None

    def list_by_thread(self, thread_id: str) -> list[dict[str, Any]]:
        raw = q.rows(
            q.order(
                self._terminals()
                .select("terminal_id,thread_id,lease_id,cwd,env_delta_json,state_version,created_at,updated_at")
                .eq("thread_id", thread_id),
                "created_at",
                desc=True,
                repo=_REPO,
                operation="list_by_thread",
            ).execute(),
            _REPO,
            "list_by_thread",
        )
        return [dict(r) for r in raw]

    def list_all(self) -> list[dict[str, Any]]:
        raw = q.rows(
            q.order(
                self._terminals().select("terminal_id,thread_id,lease_id,cwd,env_delta_json,state_version,created_at,updated_at"),
                "created_at",
                desc=True,
                repo=_REPO,
                operation="list_all",
            ).execute(),
            _REPO,
            "list_all",
        )
        return [dict(r) for r in raw]

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def _ensure_thread_pointer(self, thread_id: str, terminal_id: str) -> None:
        existing = self._get_pointer_row(thread_id)
        if existing:
            return
        now = datetime.now().isoformat()
        self._pointers().insert(
            {
                "thread_id": thread_id,
                "active_terminal_id": terminal_id,
                "default_terminal_id": terminal_id,
                "updated_at": now,
            }
        ).execute()

    def create(
        self,
        terminal_id: str,
        thread_id: str,
        lease_id: str,
        initial_cwd: str = "/root",
    ) -> dict[str, Any]:
        now = datetime.now().isoformat()
        env_delta_json = "{}"
        state_version = 0
        self._terminals().insert(
            {
                "terminal_id": terminal_id,
                "thread_id": thread_id,
                "lease_id": lease_id,
                "cwd": initial_cwd,
                "env_delta_json": env_delta_json,
                "state_version": state_version,
                "created_at": now,
                "updated_at": now,
            }
        ).execute()
        self._ensure_thread_pointer(thread_id, terminal_id)
        return {
            "terminal_id": terminal_id,
            "thread_id": thread_id,
            "lease_id": lease_id,
            "cwd": initial_cwd,
            "env_delta_json": env_delta_json,
            "state_version": state_version,
            "created_at": now,
            "updated_at": now,
        }

    def set_active(self, thread_id: str, terminal_id: str) -> None:
        # Verify terminal exists and belongs to thread
        terminal = self.get_by_id(terminal_id)
        if terminal is None:
            raise RuntimeError(f"Terminal {terminal_id} not found")
        if terminal["thread_id"] != thread_id:
            raise RuntimeError(f"Terminal {terminal_id} belongs to thread {terminal['thread_id']}, not thread {thread_id}")

        now = datetime.now().isoformat()
        pointer = self._get_pointer_row(thread_id)
        if pointer is None:
            self._pointers().insert(
                {
                    "thread_id": thread_id,
                    "active_terminal_id": terminal_id,
                    "default_terminal_id": terminal_id,
                    "updated_at": now,
                }
            ).execute()
        else:
            self._pointers().update(
                {
                    "active_terminal_id": terminal_id,
                    "updated_at": now,
                }
            ).eq("thread_id", thread_id).execute()

    def delete_by_thread(self, thread_id: str) -> None:
        for terminal in self.list_by_thread(thread_id):
            self.delete(str(terminal["terminal_id"]))

    def delete(self, terminal_id: str) -> None:
        terminal = self.get_by_id(terminal_id)
        if terminal is None:
            return
        thread_id = str(terminal["thread_id"])
        pointer = self._get_pointer_row(thread_id)
        remaining = [row for row in self.list_by_thread(thread_id) if str(row["terminal_id"]) != terminal_id]

        # @@@pointer-before-terminal-delete - Supabase now enforces thread_terminal_pointers FKs,
        # so pointer rows must stop referencing the terminal before the terminal row is deleted.
        if pointer is not None:
            if not remaining:
                self._pointers().delete().eq("thread_id", thread_id).execute()
            else:
                next_terminal_id = str(remaining[0]["terminal_id"])
                active_terminal_id = str(pointer["active_terminal_id"])
                default_terminal_id = str(pointer["default_terminal_id"])
                self._pointers().update(
                    {
                        "active_terminal_id": next_terminal_id if active_terminal_id == terminal_id else active_terminal_id,
                        "default_terminal_id": next_terminal_id if default_terminal_id == terminal_id else default_terminal_id,
                        "updated_at": datetime.now().isoformat(),
                    }
                ).eq("thread_id", thread_id).execute()

        # Delete associated command chunks and commands (best-effort via chat_session_repo pattern)
        self._client.table("terminal_command_chunks").delete().in_(
            "command_id",
            # subquery via RPC is not available in supabase-py directly; use a select first
            [
                r["command_id"]
                for r in q.rows(
                    self._client.table("terminal_commands").select("command_id").eq("terminal_id", terminal_id).execute(),
                    _REPO,
                    "delete chunks pre-select",
                )
            ],
        ).execute()
        self._client.table("terminal_commands").delete().eq("terminal_id", terminal_id).execute()
        self._terminals().delete().eq("terminal_id", terminal_id).execute()
