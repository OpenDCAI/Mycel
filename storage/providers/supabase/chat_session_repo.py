from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from storage.providers.supabase import _query as q

_REPO = "chat session repo"
_SCHEMA = "container"
_SESSIONS = "chat_sessions"
_COMMANDS = "terminal_commands"
_CHUNKS = "terminal_command_chunks"
_TERMINALS = "abstract_terminals"
_ACTIVE_STATUSES = ["active", "idle", "paused"]
_SESSION_COLS = (
    "chat_session_id,thread_id,terminal_id,sandbox_runtime_id,runtime_id,status,"
    "idle_ttl_sec,max_duration_sec,budget_json,started_at,last_active_at,ended_at,close_reason"
)
_COMMAND_COLS = "command_id,terminal_id,chat_session_id,command_line,cwd,status,stdout,stderr,exit_code,created_at,updated_at,finished_at"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _session_row(row: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    result["session_id"] = result.pop("chat_session_id")
    return result


class SupabaseChatSessionRepo:
    def __init__(self, client: Any) -> None:
        self._client = q.validate_client(client, _REPO)

    def close(self) -> None:
        return None

    def _sessions(self) -> Any:
        return q.schema_table(self._client, _SCHEMA, _SESSIONS, _REPO)

    def _commands(self) -> Any:
        return q.schema_table(self._client, _SCHEMA, _COMMANDS, _REPO)

    def _chunks(self) -> Any:
        return q.schema_table(self._client, _SCHEMA, _CHUNKS, _REPO)

    def _terminals(self) -> Any:
        return q.schema_table(self._client, _SCHEMA, _TERMINALS, _REPO)

    def _active_query(self, operation: str) -> Any:
        return q.in_(self._sessions().select(_SESSION_COLS), "status", _ACTIVE_STATUSES, _REPO, operation)

    def get_session(self, thread_id: str, terminal_id: str | None = None) -> dict[str, Any] | None:
        query = self._active_query("get session").eq("thread_id", thread_id)
        if terminal_id is not None:
            query = query.eq("terminal_id", terminal_id)
        rows = q.rows(
            q.limit(q.order(query, "started_at", desc=True, repo=_REPO, operation="get session"), 1, _REPO, "get session").execute(),
            _REPO,
            "get session",
        )
        return _session_row(rows[0]) if rows else None

    def get_session_by_id(self, session_id: str) -> dict[str, Any] | None:
        rows = q.rows(
            q.limit(self._sessions().select(_SESSION_COLS).eq("chat_session_id", session_id), 1, _REPO, "get session by id").execute(),
            _REPO,
            "get session by id",
        )
        return _session_row(rows[0]) if rows else None

    def load_status(self, session_id: str) -> str | None:
        row = self.get_session_by_id(session_id)
        return str(row.get("status")) if row else None

    def get_session_policy(self, session_id: str) -> dict[str, Any] | None:
        row = self.get_session_by_id(session_id)
        if row is None:
            return None
        return {"idle_ttl_sec": row["idle_ttl_sec"], "max_duration_sec": row["max_duration_sec"]}

    def list_active(self) -> list[dict[str, Any]]:
        rows = q.rows(
            q.order(self._active_query("list active"), "started_at", desc=True, repo=_REPO, operation="list active").execute(),
            _REPO,
            "list active",
        )
        return [_session_row(row) for row in rows]

    def list_all(self) -> list[dict[str, Any]]:
        rows = q.rows(
            q.order(self._sessions().select(_SESSION_COLS), "started_at", desc=True, repo=_REPO, operation="list all").execute(),
            _REPO,
            "list all",
        )
        return [_session_row(row) for row in rows]

    def create_session(
        self,
        session_id: str,
        thread_id: str,
        terminal_id: str,
        sandbox_runtime_id: str,
        *,
        runtime_id: str | None = None,
        status: str = "active",
        idle_ttl_sec: int = 600,
        max_duration_sec: int = 86400,
        budget_json: str | None = None,
        started_at: str | None = None,
        last_active_at: str | None = None,
    ) -> dict[str, Any]:
        now = started_at or _now()
        last_active = last_active_at or now
        for row in self._sessions_for_terminal(terminal_id, active_only=True):
            self._sessions().update({"status": "closed", "ended_at": now, "close_reason": "superseded"}).eq(
                "chat_session_id", row["chat_session_id"]
            ).execute()
        payload = {
            "chat_session_id": session_id,
            "thread_id": thread_id,
            "terminal_id": terminal_id,
            "sandbox_runtime_id": sandbox_runtime_id,
            "runtime_id": runtime_id,
            "status": status,
            "idle_ttl_sec": idle_ttl_sec,
            "max_duration_sec": max_duration_sec,
            "budget_json": budget_json,
            "started_at": now,
            "last_active_at": last_active,
            "ended_at": None,
            "close_reason": None,
        }
        self._sessions().insert(payload).execute()
        return _session_row(payload)

    def _sessions_for_terminal(self, terminal_id: str, *, active_only: bool) -> list[dict[str, Any]]:
        query = self._sessions().select(_SESSION_COLS).eq("terminal_id", terminal_id)
        if active_only:
            query = q.in_(query, "status", _ACTIVE_STATUSES, _REPO, "sessions for terminal")
        return q.rows(query.execute(), _REPO, "sessions for terminal")

    def touch(self, session_id: str, last_active_at: str | None = None, status: str | None = None) -> None:
        payload: dict[str, Any] = {"last_active_at": last_active_at or _now()}
        if status is not None:
            payload["status"] = status
        self._sessions().update(payload).eq("chat_session_id", session_id).execute()

    def touch_thread_activity(self, thread_id: str, last_active_at: str | None = None) -> None:
        now = last_active_at or _now()
        for row in q.rows(
            self._sessions().select(_SESSION_COLS).eq("thread_id", thread_id).neq("status", "closed").execute(), _REPO, "touch thread"
        ):
            self._sessions().update({"last_active_at": now}).eq("chat_session_id", row["chat_session_id"]).execute()

    def pause(self, session_id: str) -> None:
        self._sessions().update({"status": "paused", "close_reason": "paused"}).eq("chat_session_id", session_id).execute()

    def resume(self, session_id: str) -> None:
        self._sessions().update({"status": "active", "close_reason": None}).eq("chat_session_id", session_id).execute()

    def upsert_command(
        self,
        *,
        command_id: str,
        terminal_id: str,
        chat_session_id: str | None,
        command_line: str,
        cwd: str,
        status: str,
        stdout: str,
        stderr: str,
        exit_code: int | None,
        updated_at: str,
        finished_at: str | None,
        created_at: str | None = None,
    ) -> None:
        existing = self._command_by_id(command_id)
        if existing is not None:
            self._commands().update(
                {
                    "status": status,
                    "stdout": stdout,
                    "stderr": stderr,
                    "exit_code": exit_code,
                    "updated_at": updated_at,
                    "finished_at": finished_at,
                }
            ).eq("command_id", command_id).execute()
            return
        self._commands().insert(
            {
                "command_id": command_id,
                "terminal_id": terminal_id,
                "chat_session_id": chat_session_id,
                "command_line": command_line,
                "cwd": cwd,
                "status": status,
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": exit_code,
                "created_at": created_at or updated_at,
                "updated_at": updated_at,
                "finished_at": finished_at,
            }
        ).execute()

    def _command_by_id(self, command_id: str) -> dict[str, Any] | None:
        rows = q.rows(
            q.limit(self._commands().select(_COMMAND_COLS).eq("command_id", command_id), 1, _REPO, "command by id").execute(),
            _REPO,
            "command by id",
        )
        return dict(rows[0]) if rows else None

    def append_command_chunks(self, *, command_id: str, stdout_chunks: list[str], stderr_chunks: list[str], created_at: str) -> None:
        payloads = [
            {"command_id": command_id, "stream": "stdout", "content": chunk, "created_at": created_at} for chunk in stdout_chunks
        ] + [{"command_id": command_id, "stream": "stderr", "content": chunk, "created_at": created_at} for chunk in stderr_chunks]
        if payloads:
            self._chunks().insert(payloads).execute()

    def get_command(self, *, command_id: str, terminal_id: str) -> dict[str, Any] | None:
        rows = q.rows(
            q.limit(
                self._commands().select(_COMMAND_COLS).eq("command_id", command_id).eq("terminal_id", terminal_id),
                1,
                _REPO,
                "get command",
            ).execute(),
            _REPO,
            "get command",
        )
        return dict(rows[0]) if rows else None

    def list_command_chunks(self, *, command_id: str) -> list[dict[str, Any]]:
        rows = q.rows(
            q.order(
                self._chunks().select("stream,content,chunk_id").eq("command_id", command_id),
                "chunk_id",
                desc=False,
                repo=_REPO,
                operation="chunks",
            ).execute(),
            _REPO,
            "chunks",
        )
        return [{"stream": row["stream"], "content": row["content"]} for row in rows]

    def find_command_terminal_id(self, *, command_id: str, thread_id: str) -> str | None:
        command = self._command_by_id(command_id)
        if command is None:
            return None
        terminal_id = str(command.get("terminal_id") or "")
        terminal = self._terminal_by_id(terminal_id)
        if terminal is None or terminal.get("thread_id") != thread_id:
            return None
        return terminal_id

    def _terminal_by_id(self, terminal_id: str) -> dict[str, Any] | None:
        rows = q.rows(
            q.limit(
                self._terminals().select("terminal_id,thread_id,sandbox_runtime_id").eq("terminal_id", terminal_id),
                1,
                _REPO,
                "terminal by id",
            ).execute(),
            _REPO,
            "terminal by id",
        )
        return dict(rows[0]) if rows else None

    def delete_session(self, session_id: str, *, reason: str = "closed") -> None:
        self._sessions().update({"status": "closed", "ended_at": _now(), "close_reason": reason}).eq(
            "chat_session_id", session_id
        ).execute()

    def delete_by_thread(self, thread_id: str) -> None:
        terminals = q.rows(self._terminals().select("terminal_id").eq("thread_id", thread_id).execute(), _REPO, "thread terminals")
        terminal_ids = [str(row["terminal_id"]) for row in terminals]
        if terminal_ids:
            commands = q.rows_in_chunks(
                lambda: self._commands().select("command_id"), "terminal_id", terminal_ids, _REPO, "thread commands"
            )
            command_ids = [str(row["command_id"]) for row in commands]
            if command_ids:
                q.execute_in_chunks(lambda: self._chunks().delete(), "command_id", command_ids, _REPO, "delete command chunks")
            q.execute_in_chunks(lambda: self._commands().delete(), "terminal_id", terminal_ids, _REPO, "delete commands")
        self._sessions().delete().eq("thread_id", thread_id).execute()

    def terminal_has_running_command(self, terminal_id: str) -> bool:
        rows = q.rows(
            q.limit(
                self._commands().select("command_id").eq("terminal_id", terminal_id).eq("status", "running"),
                1,
                _REPO,
                "terminal running command",
            ).execute(),
            _REPO,
            "terminal running command",
        )
        return bool(rows)

    def sandbox_runtime_has_running_command(self, sandbox_runtime_id: str) -> bool:
        terminals = q.rows(
            self._terminals().select("terminal_id").eq("sandbox_runtime_id", sandbox_runtime_id).execute(), _REPO, "runtime terminals"
        )
        terminal_ids = [str(row["terminal_id"]) for row in terminals]
        if not terminal_ids:
            return False
        for chunk in q.value_chunks(terminal_ids):
            rows = q.rows(
                q.limit(
                    q.in_(
                        self._commands().select("command_id").eq("status", "running"),
                        "terminal_id",
                        chunk,
                        _REPO,
                        "runtime running command",
                    ),
                    1,
                    _REPO,
                    "runtime running command",
                ).execute(),
                _REPO,
                "runtime running command",
            )
            if rows:
                return True
        return False

    def close_all_active(self, reason: str, ended_at: str | None = None) -> None:
        ts = ended_at or _now()
        for row in self.list_active():
            self._sessions().update({"status": "closed", "ended_at": ts, "close_reason": reason}).eq(
                "chat_session_id", row["session_id"]
            ).execute()

    def cleanup_expired(self) -> list[str]:
        active = self.list_active()
        now = datetime.now(UTC)
        expired: list[str] = []
        for session in active:
            started_at = datetime.fromisoformat(session["started_at"])
            last_active_at = datetime.fromisoformat(session["last_active_at"])
            if (now - last_active_at).total_seconds() > int(session.get("idle_ttl_sec") or 0):
                expired.append(session["session_id"])
                continue
            if (now - started_at).total_seconds() > int(session.get("max_duration_sec") or 0):
                expired.append(session["session_id"])
        return expired
