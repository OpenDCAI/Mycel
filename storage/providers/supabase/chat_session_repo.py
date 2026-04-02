"""Supabase repository for chat session persistence."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from storage.providers.supabase import _query as q

_REPO = "chat session repo"
_SESSIONS_TABLE = "chat_sessions"
_COMMANDS_TABLE = "terminal_commands"
_CHUNKS_TABLE = "terminal_command_chunks"


class SupabaseChatSessionRepo:
    """Chat session CRUD backed by Supabase.

    Returns raw dicts — domain object construction is the consumer's job.
    """

    def __init__(self, client: Any) -> None:
        self._client = q.validate_client(client, _REPO)

    def close(self) -> None:
        return None

    def ensure_tables(self) -> None:
        # Tables are managed by Supabase migrations; no-op here.
        return None

    def _sessions(self) -> Any:
        return self._client.table(_SESSIONS_TABLE)

    def _commands(self) -> Any:
        return self._client.table(_COMMANDS_TABLE)

    def _chunks(self) -> Any:
        return self._client.table(_CHUNKS_TABLE)

    # ------------------------------------------------------------------
    # Session column projection
    # ------------------------------------------------------------------
    _SESSION_COLS = (
        "chat_session_id,thread_id,terminal_id,lease_id,"
        "runtime_id,status,idle_ttl_sec,max_duration_sec,"
        "budget_json,started_at,last_active_at,ended_at,close_reason"
    )

    @staticmethod
    def _normalize_session(row: dict[str, Any]) -> dict[str, Any]:
        """Rename chat_session_id -> session_id for caller compatibility."""
        result = dict(row)
        if "chat_session_id" in result and "session_id" not in result:
            result["session_id"] = result.pop("chat_session_id")
        return result

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def get_session(self, thread_id: str, terminal_id: str | None = None) -> dict[str, Any] | None:
        query = self._sessions().select(self._SESSION_COLS).eq("thread_id", thread_id)
        if terminal_id is not None:
            query = query.eq("terminal_id", terminal_id)
        # Filter active statuses via in_
        query = q.in_(query, "status", ["active", "idle", "paused"], _REPO, "get_session")
        raw = q.rows(
            q.limit(
                q.order(query, "started_at", desc=True, repo=_REPO, operation="get_session"),
                1,
                _REPO,
                "get_session",
            ).execute(),
            _REPO,
            "get_session",
        )
        return self._normalize_session(raw[0]) if raw else None

    def get_session_by_id(self, session_id: str) -> dict[str, Any] | None:
        raw = q.rows(
            q.limit(
                self._sessions().select(self._SESSION_COLS).eq("chat_session_id", session_id),
                1,
                _REPO,
                "get_session_by_id",
            ).execute(),
            _REPO,
            "get_session_by_id",
        )
        return self._normalize_session(raw[0]) if raw else None

    def get_session_policy(self, session_id: str) -> dict[str, Any] | None:
        raw = q.rows(
            self._sessions()
            .select("idle_ttl_sec,max_duration_sec")
            .eq("chat_session_id", session_id)
            .execute(),
            _REPO,
            "get_session_policy",
        )
        return dict(raw[0]) if raw else None

    def load_status(self, session_id: str) -> str | None:
        raw = q.rows(
            self._sessions().select("status").eq("chat_session_id", session_id).execute(),
            _REPO,
            "load_status",
        )
        return str(raw[0]["status"]) if raw else None

    def list_active(self) -> list[dict[str, Any]]:
        raw = q.rows(
            q.order(
                q.in_(
                    self._sessions().select(self._SESSION_COLS),
                    "status",
                    ["active", "idle", "paused"],
                    _REPO,
                    "list_active",
                ),
                "started_at",
                desc=True,
                repo=_REPO,
                operation="list_active",
            ).execute(),
            _REPO,
            "list_active",
        )
        return [self._normalize_session(r) for r in raw]

    def list_all(self) -> list[dict[str, Any]]:
        raw = q.rows(
            q.order(
                self._sessions().select(
                    "chat_session_id,thread_id,terminal_id,lease_id,"
                    "runtime_id,status,budget_json,started_at,last_active_at,ended_at,close_reason"
                ),
                "started_at",
                desc=True,
                repo=_REPO,
                operation="list_all",
            ).execute(),
            _REPO,
            "list_all",
        )
        return [self._normalize_session(r) for r in raw]

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def create_session(
        self,
        session_id: str,
        thread_id: str,
        terminal_id: str,
        lease_id: str,
        *,
        runtime_id: str | None = None,
        status: str = "active",
        idle_ttl_sec: int = 600,
        max_duration_sec: int = 86400,
        budget_json: str | None = None,
        started_at: str | None = None,
        last_active_at: str | None = None,
    ) -> dict[str, Any]:
        now_iso = started_at or datetime.now().isoformat()
        last_active = last_active_at or now_iso

        # Supersede any existing active sessions for this terminal
        self._sessions().update(
            {"status": "closed", "ended_at": now_iso, "close_reason": "superseded"}
        ).eq("terminal_id", terminal_id).in_("status", ["active", "idle", "paused"]).execute()

        self._sessions().insert(
            {
                "chat_session_id": session_id,
                "thread_id": thread_id,
                "terminal_id": terminal_id,
                "lease_id": lease_id,
                "runtime_id": runtime_id,
                "status": status,
                "idle_ttl_sec": idle_ttl_sec,
                "max_duration_sec": max_duration_sec,
                "budget_json": budget_json,
                "started_at": now_iso,
                "last_active_at": last_active,
                "ended_at": None,
                "close_reason": None,
            }
        ).execute()

        return {
            "session_id": session_id,
            "thread_id": thread_id,
            "terminal_id": terminal_id,
            "lease_id": lease_id,
            "runtime_id": runtime_id,
            "status": status,
            "idle_ttl_sec": idle_ttl_sec,
            "max_duration_sec": max_duration_sec,
            "budget_json": budget_json,
            "started_at": now_iso,
            "last_active_at": last_active,
            "ended_at": None,
            "close_reason": None,
        }

    def touch(self, session_id: str, last_active_at: str | None = None, status: str | None = None) -> None:
        now = last_active_at or datetime.now().isoformat()
        update: dict[str, Any] = {"last_active_at": now}
        if status is not None:
            update["status"] = status
        self._sessions().update(update).eq("chat_session_id", session_id).execute()

    def touch_thread_activity(self, thread_id: str, last_active_at: str | None = None) -> None:
        now = last_active_at or datetime.now().isoformat()
        self._sessions().update({"last_active_at": now}).eq("thread_id", thread_id).neq("status", "closed").execute()

    def pause(self, session_id: str) -> None:
        self._sessions().update(
            {"status": "paused", "close_reason": "paused"}
        ).eq("chat_session_id", session_id).in_("status", ["active", "idle"]).execute()

    def resume(self, session_id: str) -> None:
        self._sessions().update(
            {"status": "active", "close_reason": None}
        ).eq("chat_session_id", session_id).eq("status", "paused").execute()

    def delete_session(self, session_id: str, *, reason: str = "closed") -> None:
        self._sessions().update(
            {"status": "closed", "ended_at": datetime.now().isoformat(), "close_reason": reason}
        ).eq("chat_session_id", session_id).in_("status", ["active", "idle", "paused"]).execute()

    def delete_by_thread(self, thread_id: str) -> None:
        # Find terminal_ids for this thread
        terminal_rows = q.rows(
            self._client.table("abstract_terminals").select("terminal_id").eq("thread_id", thread_id).execute(),
            _REPO,
            "delete_by_thread terminal lookup",
        )
        terminal_ids = [str(r["terminal_id"]) for r in terminal_rows]

        if terminal_ids:
            # Find command_ids for these terminals
            command_rows = q.rows(
                q.in_(
                    self._commands().select("command_id"),
                    "terminal_id",
                    terminal_ids,
                    _REPO,
                    "delete_by_thread command lookup",
                ).execute(),
                _REPO,
                "delete_by_thread command lookup",
            )
            command_ids = [str(r["command_id"]) for r in command_rows]

            if command_ids:
                q.in_(
                    self._chunks().delete(), "command_id", command_ids, _REPO, "delete_by_thread chunks"
                ).execute()

            q.in_(
                self._commands().delete(), "terminal_id", terminal_ids, _REPO, "delete_by_thread commands"
            ).execute()

        self._sessions().delete().eq("thread_id", thread_id).execute()

    def terminal_has_running_command(self, terminal_id: str) -> bool:
        raw = q.rows(
            q.limit(
                self._commands().select("command_id").eq("terminal_id", terminal_id).eq("status", "running"),
                1,
                _REPO,
                "terminal_has_running_command",
            ).execute(),
            _REPO,
            "terminal_has_running_command",
        )
        return len(raw) > 0

    def lease_has_running_command(self, lease_id: str) -> bool:
        # Find all terminals for this lease, then check for running commands
        terminal_rows = q.rows(
            self._client.table("abstract_terminals").select("terminal_id").eq("lease_id", lease_id).execute(),
            _REPO,
            "lease_has_running_command terminal lookup",
        )
        terminal_ids = [str(r["terminal_id"]) for r in terminal_rows]
        if not terminal_ids:
            return False
        raw = q.rows(
            q.limit(
                q.in_(
                    self._commands().select("command_id").eq("status", "running"),
                    "terminal_id",
                    terminal_ids,
                    _REPO,
                    "lease_has_running_command",
                ),
                1,
                _REPO,
                "lease_has_running_command",
            ).execute(),
            _REPO,
            "lease_has_running_command",
        )
        return len(raw) > 0

    def cleanup_expired(self) -> list[str]:
        active = self.list_active()
        now = datetime.now()
        expired_ids: list[str] = []
        for session in active:
            started_at = datetime.fromisoformat(session["started_at"])
            last_active_at = datetime.fromisoformat(session["last_active_at"])
            idle_ttl_sec = session.get("idle_ttl_sec", 0)
            max_duration_sec = session.get("max_duration_sec", 0)
            policy = self.get_session_policy(session["session_id"])
            if policy:
                idle_ttl_sec = policy["idle_ttl_sec"]
                max_duration_sec = policy["max_duration_sec"]
            idle_elapsed = (now - last_active_at).total_seconds()
            total_elapsed = (now - started_at).total_seconds()
            if idle_elapsed > idle_ttl_sec or total_elapsed > max_duration_sec:
                expired_ids.append(session["session_id"])
        return expired_ids
