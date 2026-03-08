"""Sandbox session manager.

Orchestrates: Thread → ChatSession → Runtime → Terminal → Lease → Instance
"""

import logging
import sqlite3
import uuid
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

from storage.providers.sqlite.kernel import connect_sqlite

from sandbox.capability import SandboxCapability
from sandbox.chat_session import ChatSessionManager, ChatSessionPolicy
from sandbox.config import DEFAULT_DB_PATH
from sandbox.lease import LeaseStore
from sandbox.provider import SandboxProvider
from sandbox.terminal import TerminalState, TerminalStore
from sandbox.sync.manager import SyncManager


def lookup_sandbox_for_thread(thread_id: str, db_path: Path | None = None) -> str | None:
    target_db = db_path or DEFAULT_DB_PATH
    if not target_db.exists():
        return None

    with connect_sqlite(target_db, timeout_ms=5_000) as conn:
        existing = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        if "abstract_terminals" not in existing or "sandbox_leases" not in existing:
            return None

        row = conn.execute(
            """
            SELECT sl.provider_name
            FROM abstract_terminals at
            JOIN sandbox_leases sl ON at.lease_id = sl.lease_id
            WHERE at.thread_id = ?
            LIMIT 1
            """,
            (thread_id,),
        ).fetchone()
        return row[0] if row else None


class SandboxManager:
    def __init__(
        self,
        provider: SandboxProvider,
        db_path: Path | None = None,
        on_session_ready: Callable[[str, str], None] | None = None,
        workspace_root: Path | None = None,
    ):
        self.provider = provider
        self.provider_capability = provider.get_capability()
        self._on_session_ready = on_session_ready

        self.db_path = db_path or DEFAULT_DB_PATH
        self.terminal_store = TerminalStore(db_path=self.db_path)
        self.lease_store = LeaseStore(db_path=self.db_path)
        self.session_manager = ChatSessionManager(
            provider=provider,
            db_path=self.db_path,
            default_policy=ChatSessionPolicy(),
        )

        _ws_root = workspace_root or Path.home() / ".leon" / "thread_files"
        self.workspace_sync = SyncManager(
            provider_capability=self.provider_capability,
            workspace_root=_ws_root,
        )

    def _default_terminal_cwd(self) -> str:
        for attr in ("default_cwd", "default_context_path", "mount_path"):
            if hasattr(self.provider, attr):
                value = getattr(self.provider, attr)
                if isinstance(value, str) and value:
                    return value
        return "/home/user"

    def _fire_session_ready(self, session_id: str, reason: str) -> None:
        if self._on_session_ready:
            self._on_session_ready(session_id, reason)

    def _ensure_bound_instance(self, lease) -> None:
        if self.provider_capability.eager_instance_binding and not lease.get_instance():
            lease.ensure_active_instance(self.provider)

    def _assert_lease_provider(self, lease, thread_id: str) -> None:
        if lease.provider_name != self.provider.name:
            raise RuntimeError(
                f"Thread {thread_id} is bound to provider {lease.provider_name}, "
                f"but current manager provider is {self.provider.name}. "
                "Use the matching sandbox type for this thread or recreate the thread."
            )

    def _get_active_terminal(self, thread_id: str):
        terminal = self.terminal_store.get_active(thread_id)
        if terminal:
            return terminal
        thread_terminals = self.terminal_store.list_by_thread(thread_id)
        # @@@thread-pointer-consistency - If terminals exist but no active pointer, DB is inconsistent and must fail loudly.
        if thread_terminals:
            raise RuntimeError(f"Thread {thread_id} has terminals but no active terminal pointer")
        return None

    def _get_active_session(self, thread_id: str):
        terminal = self._get_active_terminal(thread_id)
        if not terminal:
            return None
        return self.session_manager.get(thread_id, terminal.terminal_id)

    def _get_thread_terminals(self, thread_id: str):
        return self.terminal_store.list_by_thread(thread_id)

    def _get_thread_lease(self, thread_id: str):
        terminals = self._get_thread_terminals(thread_id)
        if not terminals:
            return None
        lease_ids = {terminal.lease_id for terminal in terminals}
        # @@@thread-single-lease-invariant - Terminals created via non-block must share one lease per thread.
        if len(lease_ids) != 1:
            raise RuntimeError(f"Thread {thread_id} has inconsistent lease_ids: {sorted(lease_ids)}")
        lease_id = next(iter(lease_ids))
        lease = self.lease_store.get(lease_id)
        if lease is None:
            return None
        self._assert_lease_provider(lease, thread_id)
        return lease

    def _thread_belongs_to_provider(self, thread_id: str) -> bool:
        terminals = self._get_thread_terminals(thread_id)
        if not terminals:
            return False
        lease = self.lease_store.get(terminals[0].lease_id)
        return bool(lease and lease.provider_name == self.provider.name)

    def close(self):
        self.session_manager.close(reason="manager_close")

    def get_sandbox(self, thread_id: str) -> SandboxCapability:
        from sandbox.thread_context import set_current_thread_id
        set_current_thread_id(thread_id)

        terminal = self._get_active_terminal(thread_id)
        session = self.session_manager.get(thread_id, terminal.terminal_id) if terminal else None
        if session:
            self._assert_lease_provider(session.lease, thread_id)
            # @@@activity-resume - Any new activity against a paused thread must resume before command execution.
            if session.status == "paused":
                if not self.resume_session(thread_id):
                    raise RuntimeError(f"Failed to resume paused session for thread {thread_id}")
                session = self.session_manager.get(thread_id, session.terminal.terminal_id)
                if not session:
                    raise RuntimeError(f"Session disappeared after resume for thread {thread_id}")
                self._assert_lease_provider(session.lease, thread_id)
            # Stamp bind_mounts on lease so lazy creation paths pick them up
            if bind_mounts:
                session.lease.bind_mounts = bind_mounts
            self._ensure_bound_instance(session.lease, bind_mounts=bind_mounts)
            return SandboxCapability(session, manager=self)

        if not terminal:
            terminal_id = f"term-{uuid.uuid4().hex[:12]}"
            lease_id = f"lease-{uuid.uuid4().hex[:12]}"
            lease = self.lease_store.create(lease_id, self.provider.name)
            initial_cwd = self._default_terminal_cwd()
            terminal = self.terminal_store.create(
                terminal_id=terminal_id,
                thread_id=thread_id,
                lease_id=lease_id,
                initial_cwd=initial_cwd,
            )
        else:
            lease = self.lease_store.get(terminal.lease_id)
            if not lease:
                lease = self.lease_store.create(terminal.lease_id, self.provider.name)
            self._assert_lease_provider(lease, thread_id)

        # Stamp bind_mounts on lease so lazy creation paths pick them up
        if bind_mounts:
            lease.bind_mounts = bind_mounts
        self._ensure_bound_instance(lease, bind_mounts=bind_mounts)

        session_id = f"sess-{uuid.uuid4().hex[:12]}"
        session = self.session_manager.create(
            session_id=session_id,
            thread_id=thread_id,
            terminal=terminal,
            lease=lease,
        )

        instance = lease.get_instance()
        if instance:
            # @@@workspace-upload - sync files to sandbox after creation
            try:
                self.workspace_sync.upload_workspace(thread_id, instance.instance_id, self.provider)
            except Exception:
                logger.warning("Failed to upload workspace on create", exc_info=True)
            self._fire_session_ready(instance.instance_id, "create")

        return SandboxCapability(session, manager=self)


    def create_background_command_session(self, thread_id: str, initial_cwd: str) -> Any:
        default_terminal = self.terminal_store.get_default(thread_id)
        if default_terminal is None:
            # Fallback: pointer row may predate default_terminal_id tracking; try active terminal
            default_terminal = self.terminal_store.get_active(thread_id)
        if default_terminal is None:
            raise RuntimeError(f"Thread {thread_id} has no default terminal")
        lease = self.lease_store.get(default_terminal.lease_id)
        if lease is None:
            raise RuntimeError(f"Missing lease {default_terminal.lease_id} for thread {thread_id}")
        self._assert_lease_provider(lease, thread_id)

        inherited = default_terminal.get_state()
        terminal_id = f"term-{uuid.uuid4().hex[:12]}"
        terminal = self.terminal_store.create(
            terminal_id=terminal_id,
            thread_id=thread_id,
            lease_id=lease.lease_id,
            initial_cwd=initial_cwd,
        )
        # @@@async-terminal-inherit-state - non-blocking commands fork from default terminal cwd/env snapshot.
        terminal.update_state(
            TerminalState(
                cwd=initial_cwd,
                env_delta=dict(inherited.env_delta),
                state_version=inherited.state_version,
            )
        )
        session = self.session_manager.create(
            session_id=f"sess-{uuid.uuid4().hex[:12]}",
            thread_id=thread_id,
            terminal=terminal,
            lease=lease,
        )
        return session

    def _db_has_table(self, conn: sqlite3.Connection, name: str) -> bool:
        return (
            conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ? LIMIT 1",
                (name,),
            ).fetchone()
            is not None
        )

    def _terminal_is_busy(self, terminal_id: str) -> bool:
        """Return True if this terminal has a running command."""
        if not terminal_id:
            return False
        if not self.db_path.exists():
            return False
        with connect_sqlite(self.db_path) as conn:
            if not self._db_has_table(conn, "terminal_commands"):
                return False
            row = conn.execute(
                """
                SELECT 1
                FROM terminal_commands
                WHERE terminal_id = ? AND status = 'running'
                LIMIT 1
                """,
                (terminal_id,),
            ).fetchone()
            return row is not None

    def _lease_is_busy(self, lease_id: str) -> bool:
        """Return True if any terminal under this lease has a running command."""
        if not lease_id:
            return False
        if not self.db_path.exists():
            return False
        with connect_sqlite(self.db_path) as conn:
            if not self._db_has_table(conn, "terminal_commands"):
                return False
            if not self._db_has_table(conn, "abstract_terminals"):
                return False
            row = conn.execute(
                """
                SELECT 1
                FROM terminal_commands tc
                JOIN abstract_terminals at ON at.terminal_id = tc.terminal_id
                WHERE at.lease_id = ? AND tc.status = 'running'
                LIMIT 1
                """,
                (lease_id,),
            ).fetchone()
            return row is not None

    def _is_expired(self, session_row: dict, now: datetime) -> bool:
        started_at_raw = session_row.get("started_at")
        last_active_raw = session_row.get("last_active_at")
        if not started_at_raw or not last_active_raw:
            return False
        started_at = datetime.fromisoformat(str(started_at_raw))
        last_active_at = datetime.fromisoformat(str(last_active_raw))
        idle_ttl_sec = int(session_row.get("idle_ttl_sec") or 0)
        max_duration_sec = int(session_row.get("max_duration_sec") or 0)
        idle_elapsed = (now - last_active_at).total_seconds()
        total_elapsed = (now - started_at).total_seconds()
        return idle_elapsed > idle_ttl_sec or total_elapsed > max_duration_sec

    def enforce_idle_timeouts(self) -> int:
        """Pause expired leases and close chat sessions.

        Rule:
        - If a chat session is idle past idle_ttl_sec, or older than max_duration_sec:
          1) pause physical lease instance (remote providers)
          2) close chat session runtime + mark session closed
        - Local sandbox is exempt from idle timeout (no cost to keep running)
        """
        # Skip idle timeout for local sandbox
        if self.provider.name == "local":
            return 0

        now = datetime.now()
        count = 0

        active_rows = self.session_manager.list_active()

        for row in active_rows:
            session_id = row.get("session_id")
            thread_id = row.get("thread_id")
            started_at_raw = row.get("started_at")
            last_active_raw = row.get("last_active_at")
            if not session_id or not thread_id or not started_at_raw or not last_active_raw:
                continue

            started_at = datetime.fromisoformat(str(started_at_raw))
            last_active_at = datetime.fromisoformat(str(last_active_raw))
            idle_ttl_sec = int(row.get("idle_ttl_sec") or 0)
            max_duration_sec = int(row.get("max_duration_sec") or 0)

            idle_elapsed = (now - last_active_at).total_seconds()
            total_elapsed = (now - started_at).total_seconds()
            if idle_elapsed <= idle_ttl_sec and total_elapsed <= max_duration_sec:
                continue

            terminal_id = row.get("terminal_id")
            terminal = self.terminal_store.get_by_id(str(terminal_id)) if terminal_id else None
            lease = self.lease_store.get(terminal.lease_id) if terminal else None
            if lease and lease.provider_name != self.provider.name:
                continue

            if terminal and self._terminal_is_busy(terminal.terminal_id):
                continue

            if lease:
                # @@@idle-reaper-shared-lease - non-blocking commands fork background terminals but share one lease.
                # Do not pause the underlying lease if another session on the same lease is still active/idle.
                lease_id = str(row.get("lease_id") or lease.lease_id)
                has_other_active = False
                for other in active_rows:
                    if str(other.get("lease_id") or "") != lease_id:
                        continue
                    if str(other.get("session_id") or "") == str(session_id):
                        continue
                    if str(other.get("status") or "") not in {"active", "idle"}:
                        continue
                    if self._is_expired(other, now):
                        continue
                    has_other_active = True
                    break

                if not has_other_active:
                    if self._lease_is_busy(lease.lease_id):
                        continue
                    status = lease.refresh_instance_status(self.provider)
                    # Only pause remote providers (local sandbox doesn't need pause)
                    if status == "running" and self.provider.name != "local":
                        try:
                            paused = lease.pause_instance(self.provider)
                        except Exception as exc:
                            print(
                                f"[idle-reaper] failed to pause expired lease {lease.lease_id} for thread {thread_id}: {exc}"
                            )
                            continue
                        if not paused:
                            print(
                                f"[idle-reaper] failed to pause expired lease {lease.lease_id} for thread {thread_id}"
                            )
                            continue

            self.session_manager.delete(session_id, reason="idle_timeout")
            count += 1

        return count

    def get_or_create_session(self, thread_id: str):
        capability = self.get_sandbox(thread_id)
        return capability.resolve_session_info(self.provider.name)

    def pause_session(self, thread_id: str) -> bool:
        """Pause session for thread."""
        terminals = self._get_thread_terminals(thread_id)
        if not terminals:
            return False

        lease = self._get_thread_lease(thread_id)
        if not lease:
            return False

        if lease.observed_state != "paused":
            # @@@pause-rebind-instance - Pause must operate on a concrete running instance.
            # Re-resolve through lease to avoid pausing stale detached bindings.
            lease.ensure_active_instance(self.provider)
            instance = lease.get_instance()
            if instance:
                # @@@workspace-download - sync files from sandbox before pause
                try:
                    self.workspace_sync.download_workspace(thread_id, instance.instance_id, self.provider)
                except Exception:
                    logger.error("Failed to download workspace before pause — agent changes may be lost", exc_info=True)
            if not lease.pause_instance(self.provider):
                return False

        for terminal in terminals:
            session = self.session_manager.get(thread_id, terminal.terminal_id)
            if session and session.status != "paused":
                self.session_manager.pause(session.session_id)
        return True

    def _ensure_chat_session(self, thread_id: str) -> None:
        terminal = self._get_active_terminal(thread_id)
        if terminal and self.session_manager.get(thread_id, terminal.terminal_id):
            return
        self.get_sandbox(thread_id)

    def resume_session(self, thread_id: str) -> bool:
        terminals = self._get_thread_terminals(thread_id)
        if not terminals:
            return False

        lease = self._get_thread_lease(thread_id)
        if not lease:
            return False

        if not lease.resume_instance(self.provider):
            return False

        # @@@workspace-upload-on-resume - re-sync files that may have been uploaded while paused
        instance = lease.get_instance()
        if instance:
            try:
                self.workspace_sync.upload_workspace(thread_id, instance.instance_id, self.provider)
            except Exception:
                logger.warning("Failed to upload workspace on resume", exc_info=True)

        resumed_any = False
        for terminal in terminals:
            session = self.session_manager.get(thread_id, terminal.terminal_id)
            if session:
                self.session_manager.resume(session.session_id)
                resumed_any = True

        if not resumed_any:
            self._ensure_chat_session(thread_id)
        return True

    def pause_all_sessions(self) -> int:
        sessions = self.session_manager.list_all()
        count = 0
        paused_threads: set[str] = set()
        for session_data in sessions:
            thread_id = str(session_data["thread_id"])
            if thread_id in paused_threads:
                continue
            if not self._thread_belongs_to_provider(thread_id):
                continue
            paused = self.pause_session(thread_id)
            if paused:
                count += 1
                paused_threads.add(thread_id)
        return count

    def destroy_session(self, thread_id: str, session_id: str | None = None) -> bool:
        if session_id:
            sessions = self.session_manager.list_all()
            matched = next((row for row in sessions if str(row.get("session_id")) == session_id), None)
            if matched is not None and str(matched.get("thread_id") or "") != thread_id:
                matched_thread_id = str(matched.get("thread_id") or "")
                raise RuntimeError(
                    f"Session {session_id} belongs to thread {matched_thread_id}, not thread {thread_id}"
                )

        terminals = self._get_thread_terminals(thread_id)
        if not terminals:
            return False

        return self.destroy_thread_resources(thread_id)

    def destroy_thread_resources(self, thread_id: str) -> bool:
        """Destroy physical resources and detach thread from terminal/lease records."""
        terminals = self.terminal_store.list_by_thread(thread_id)
        if not terminals:
            return False

        # @@@workspace-download - sync files before destroy
        lease = self._get_thread_lease(thread_id)
        if lease:
            instance = lease.get_instance()
            if instance:
                try:
                    self.workspace_sync.download_workspace(thread_id, instance.instance_id, self.provider)
                except Exception:
                    logger.error("Failed to download workspace before destroy — agent changes are lost", exc_info=True)

        lease_ids = {terminal.lease_id for terminal in terminals}

        for terminal in terminals:
            session = self.session_manager.get(thread_id, terminal.terminal_id)
            if session:
                self.session_manager.delete(session.session_id, reason="thread_deleted")

        for terminal in terminals:
            self.terminal_store.delete(terminal.terminal_id)

        for lease_id in lease_ids:
            lease = self.lease_store.get(lease_id)
            if not lease:
                raise RuntimeError(f"Missing lease {lease_id} for thread {thread_id}")
            lease.destroy_instance(self.provider)
            lease_in_use = any(row.get("lease_id") == lease_id for row in self.terminal_store.list_all())
            if not lease_in_use:
                self.lease_store.delete(lease_id)
        return True

    def list_sessions(self) -> list[dict]:
        sessions: list[dict] = []

        terminals = self.terminal_store.list_all()
        threads_by_lease: dict[str, list[str]] = {}
        for term in terminals:
            lease_id = term.get("lease_id")
            thread_id = term.get("thread_id")
            if lease_id and thread_id:
                threads_by_lease.setdefault(lease_id, []).append(thread_id)

        rows = self.session_manager.list_all()
        active_rows = [r for r in rows if r.get("status") in {"active", "idle", "paused"}]
        chat_by_thread_lease: dict[tuple[str, str], dict] = {}
        for row in active_rows:
            thread_id = row.get("thread_id")
            lease_id = row.get("lease_id")
            if not thread_id or not lease_id:
                continue
            key = (str(thread_id), str(lease_id))
            if key not in chat_by_thread_lease:
                chat_by_thread_lease[key] = row
        inspect_visible = self.provider_capability.inspect_visible

        seen_instance_ids: set[str] = set()

        for lease_row in self.lease_store.list_by_provider(self.provider.name):
            lease_id = lease_row["lease_id"]
            lease = self.lease_store.get(lease_id)
            if not lease:
                continue

            instance = lease.get_instance()
            if not instance:
                continue

            status = lease.refresh_instance_status(self.provider)
            refreshed_instance = lease.get_instance()
            if not refreshed_instance or status in {"detached", "deleted", "stopped", "dead"}:
                continue

            seen_instance_ids.add(refreshed_instance.instance_id)
            threads = sorted(set(threads_by_lease.get(lease_id) or []))

            if not threads:
                sessions.append(
                    {
                        "session_id": refreshed_instance.instance_id,
                        "thread_id": "(untracked)",
                        "provider": self.provider.name,
                        "status": status,
                        "created_at": lease_row.get("created_at"),
                        "last_active": lease_row.get("updated_at"),
                        "lease_id": lease_id,
                        "instance_id": refreshed_instance.instance_id,
                        "chat_session_id": None,
                        "source": "lease",
                        "inspect_visible": inspect_visible,
                    }
                )
                continue

            for thread_id in threads:
                chat = chat_by_thread_lease.get((thread_id, lease_id))
                sessions.append(
                    {
                        "session_id": refreshed_instance.instance_id,
                        "thread_id": thread_id,
                        "provider": self.provider.name,
                        "status": status,
                        "created_at": lease_row.get("created_at"),
                        "last_active": (chat or {}).get("last_active_at") or lease_row.get("updated_at"),
                        "lease_id": lease_id,
                        "instance_id": refreshed_instance.instance_id,
                        "chat_session_id": (chat or {}).get("session_id"),
                        "source": "lease",
                        "inspect_visible": inspect_visible,
                    }
                )

        if hasattr(self.provider, "list_provider_sessions"):
            try:
                provider_sessions = self.provider.list_provider_sessions() or []
            except Exception:
                provider_sessions = []

            for ps in provider_sessions:
                instance_id = getattr(ps, "session_id", None)
                status = getattr(ps, "status", None) or "unknown"
                if not instance_id or status in {"deleted", "dead", "stopped"} or instance_id in seen_instance_ids:
                    continue

                sessions.append(
                    {
                        "session_id": instance_id,
                        "thread_id": "(orphan)",
                        "provider": self.provider.name,
                        "status": status,
                        "created_at": None,
                        "last_active": None,
                        "lease_id": None,
                        "instance_id": instance_id,
                        "chat_session_id": None,
                        "source": "provider_orphan",
                        "inspect_visible": inspect_visible,
                    }
                )

        return sessions
