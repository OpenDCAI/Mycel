from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from storage.providers.supabase import _query as q

_REPO = "terminal repo"
_SCHEMA = "container"
_TERMINALS = "abstract_terminals"
_POINTERS = "thread_terminal_pointers"
_TERMINAL_COLS = "terminal_id,thread_id,sandbox_runtime_id,cwd,env_delta_json,state_version,created_at,updated_at"
_POINTER_COLS = "thread_id,active_terminal_id,default_terminal_id,updated_at"


def _now() -> str:
    return datetime.now(UTC).isoformat()


class SupabaseTerminalRepo:
    def __init__(self, client: Any) -> None:
        self._client = q.validate_client(client, _REPO)

    def close(self) -> None:
        return None

    def _terminals(self) -> Any:
        return q.schema_table(self._client, _SCHEMA, _TERMINALS, _REPO)

    def _pointers(self) -> Any:
        return q.schema_table(self._client, _SCHEMA, _POINTERS, _REPO)

    def _get_pointer_row(self, thread_id: str) -> dict[str, Any] | None:
        rows = q.rows(
            q.limit(self._pointers().select(_POINTER_COLS).eq("thread_id", thread_id), 1, _REPO, "get pointer").execute(),
            _REPO,
            "get pointer",
        )
        return dict(rows[0]) if rows else None

    def get_active(self, thread_id: str) -> dict[str, Any] | None:
        pointer = self._get_pointer_row(thread_id)
        if pointer is None:
            return None
        row = self.get_by_id(str(pointer["active_terminal_id"]))
        if row is not None:
            return row
        latest = self.list_by_thread(thread_id)
        if not latest:
            return None
        self._ensure_thread_pointer(thread_id, str(latest[0]["terminal_id"]))
        return self.get_by_id(str(latest[0]["terminal_id"])) or latest[0]

    def get_default(self, thread_id: str) -> dict[str, Any] | None:
        pointer = self._get_pointer_row(thread_id)
        if pointer is None:
            return None
        row = self.get_by_id(str(pointer["default_terminal_id"]))
        if row is not None:
            return row
        latest = self.list_by_thread(thread_id)
        if not latest:
            return None
        self._ensure_thread_pointer(thread_id, str(latest[0]["terminal_id"]))
        return self.get_by_id(str(latest[0]["terminal_id"])) or latest[0]

    def get_by_id(self, terminal_id: str) -> dict[str, Any] | None:
        rows = q.rows(
            q.limit(self._terminals().select(_TERMINAL_COLS).eq("terminal_id", terminal_id), 1, _REPO, "get terminal").execute(),
            _REPO,
            "get terminal",
        )
        return dict(rows[0]) if rows else None

    def summarize_threads(self, thread_ids: list[str]) -> dict[str, dict[str, str | None]]:
        normalized_ids = [str(thread_id or "").strip() for thread_id in thread_ids if str(thread_id or "").strip()]
        if not normalized_ids:
            return {}
        summary: dict[str, dict[str, str | None]] = {
            thread_id: {"active_terminal_id": None, "latest_terminal_id": None} for thread_id in normalized_ids
        }
        pointer_rows = q.rows_in_chunks(
            lambda: self._pointers().select(_POINTER_COLS), "thread_id", normalized_ids, _REPO, "summarize pointers"
        )
        for row in pointer_rows:
            thread_id = str(row.get("thread_id") or "").strip()
            if thread_id:
                summary.setdefault(thread_id, {"active_terminal_id": None, "latest_terminal_id": None})["active_terminal_id"] = (
                    str(row.get("active_terminal_id") or "").strip() or None
                )
        terminal_rows = q.rows_in_chunks(
            lambda: self._terminals().select(_TERMINAL_COLS), "thread_id", normalized_ids, _REPO, "summarize terminals"
        )
        terminal_rows = sorted(
            terminal_rows, key=lambda row: (str(row.get("thread_id") or ""), str(row.get("created_at") or "")), reverse=True
        )
        for row in terminal_rows:
            thread_id = str(row.get("thread_id") or "").strip()
            terminal_id = str(row.get("terminal_id") or "").strip()
            if not thread_id or not terminal_id:
                continue
            bucket = summary.setdefault(thread_id, {"active_terminal_id": None, "latest_terminal_id": None})
            if bucket["latest_terminal_id"] is None:
                bucket["latest_terminal_id"] = terminal_id
        return summary

    def get_latest_by_sandbox_runtime(self, sandbox_runtime_id: str) -> dict[str, Any] | None:
        rows = q.rows(
            q.limit(
                q.order(
                    self._terminals().select(_TERMINAL_COLS).eq("sandbox_runtime_id", sandbox_runtime_id),
                    "created_at",
                    desc=True,
                    repo=_REPO,
                    operation="latest by runtime",
                ),
                1,
                _REPO,
                "latest by runtime",
            ).execute(),
            _REPO,
            "latest by runtime",
        )
        return dict(rows[0]) if rows else None

    def get_timestamps(self, terminal_id: str) -> tuple[str | None, str | None]:
        row = self.get_by_id(terminal_id)
        if row is None:
            return None, None
        return str(row.get("created_at") or "") or None, str(row.get("updated_at") or "") or None

    def list_by_thread(self, thread_id: str) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in q.rows(
                q.order(
                    self._terminals().select(_TERMINAL_COLS).eq("thread_id", thread_id),
                    "created_at",
                    desc=True,
                    repo=_REPO,
                    operation="list by thread",
                ).execute(),
                _REPO,
                "list by thread",
            )
        ]

    def list_all(self) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in q.rows(
                q.order(self._terminals().select(_TERMINAL_COLS), "created_at", desc=True, repo=_REPO, operation="list all").execute(),
                _REPO,
                "list all",
            )
        ]

    def _ensure_thread_pointer(self, thread_id: str, terminal_id: str) -> None:
        now = _now()
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
            return
        active_exists = self.get_by_id(str(pointer["active_terminal_id"])) is not None
        default_exists = self.get_by_id(str(pointer["default_terminal_id"])) is not None
        if active_exists and default_exists:
            return
        self._pointers().update(
            {
                "active_terminal_id": str(pointer["active_terminal_id"]) if active_exists else terminal_id,
                "default_terminal_id": str(pointer["default_terminal_id"]) if default_exists else terminal_id,
                "updated_at": now,
            }
        ).eq("thread_id", thread_id).execute()

    def create(self, terminal_id: str, thread_id: str, sandbox_runtime_id: str, initial_cwd: str = "/root") -> dict[str, Any]:
        now = _now()
        row = {
            "terminal_id": terminal_id,
            "thread_id": thread_id,
            "sandbox_runtime_id": sandbox_runtime_id,
            "cwd": initial_cwd,
            "env_delta_json": "{}",
            "state_version": 0,
            "created_at": now,
            "updated_at": now,
        }
        self._terminals().insert(row).execute()
        self._ensure_thread_pointer(thread_id, terminal_id)
        return dict(row)

    def persist_state(self, *, terminal_id: str, cwd: str, env_delta_json: str, state_version: int) -> None:
        self._terminals().update(
            {
                "cwd": cwd,
                "env_delta_json": env_delta_json,
                "state_version": state_version,
                "updated_at": _now(),
            }
        ).eq("terminal_id", terminal_id).execute()

    def set_active(self, thread_id: str, terminal_id: str) -> None:
        terminal = self.get_by_id(terminal_id)
        if terminal is None:
            raise RuntimeError(f"Terminal {terminal_id} not found")
        if terminal["thread_id"] != thread_id:
            raise RuntimeError(f"Terminal {terminal_id} belongs to thread {terminal['thread_id']}, not thread {thread_id}")
        pointer = self._get_pointer_row(thread_id)
        if pointer is None:
            self._pointers().insert(
                {
                    "thread_id": thread_id,
                    "active_terminal_id": terminal_id,
                    "default_terminal_id": terminal_id,
                    "updated_at": _now(),
                }
            ).execute()
            return
        self._pointers().update({"active_terminal_id": terminal_id, "updated_at": _now()}).eq("thread_id", thread_id).execute()

    def delete_by_thread(self, thread_id: str) -> None:
        for terminal in self.list_by_thread(thread_id):
            self.delete(str(terminal["terminal_id"]))

    def delete(self, terminal_id: str) -> None:
        terminal = self.get_by_id(terminal_id)
        if terminal is None:
            return
        thread_id = str(terminal["thread_id"])
        commands = q.rows(self._commands().select("command_id").eq("terminal_id", terminal_id).execute(), _REPO, "terminal commands")
        command_ids = [str(row["command_id"]) for row in commands]
        if command_ids:
            q.execute_in_chunks(lambda: self._chunks().delete(), "command_id", command_ids, _REPO, "delete terminal command chunks")
        self._commands().delete().eq("terminal_id", terminal_id).execute()
        self._terminals().delete().eq("terminal_id", terminal_id).execute()
        pointer = self._get_pointer_row(thread_id)
        if pointer is None:
            return
        remaining = self.list_by_thread(thread_id)
        if not remaining:
            self._pointers().delete().eq("thread_id", thread_id).execute()
            return
        next_terminal_id = str(remaining[0]["terminal_id"])
        self._pointers().update(
            {
                "active_terminal_id": next_terminal_id
                if str(pointer["active_terminal_id"]) == terminal_id
                else str(pointer["active_terminal_id"]),
                "default_terminal_id": next_terminal_id
                if str(pointer["default_terminal_id"]) == terminal_id
                else str(pointer["default_terminal_id"]),
                "updated_at": _now(),
            }
        ).eq("thread_id", thread_id).execute()

    def _commands(self) -> Any:
        return q.schema_table(self._client, _SCHEMA, "terminal_commands", _REPO)

    def _chunks(self) -> Any:
        return q.schema_table(self._client, _SCHEMA, "terminal_command_chunks", _REPO)
