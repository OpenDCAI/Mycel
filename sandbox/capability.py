"""SandboxCapability - Wrapper that hides new architecture from agents.

This module provides the capability object that agents interact with.
It wraps the new architecture (ChatSession → Runtime → Terminal → Lease)
while maintaining the same interface as before.
"""

from __future__ import annotations

import shlex
import sqlite3
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from sandbox.interfaces.executor import AsyncCommand, BaseExecutor, ExecuteResult
from sandbox.interfaces.filesystem import FileSystemBackend

if TYPE_CHECKING:
    from sandbox.chat_session import ChatSession
    from sandbox.manager import SandboxManager


class SandboxCapability:
    """Agent-facing capability object.

    Wraps ChatSession and provides access to command execution and filesystem.
    Agents see the same interface as before - all complexity is hidden.

    Usage:
        sandbox = sandbox_manager.get_sandbox(thread_id)
        result = await sandbox.command.execute("ls")
        content = sandbox.fs.read_file("/path/to/file")
    """

    def __init__(self, session: ChatSession, manager: SandboxManager | None = None):
        self._session = session
        self._command_wrapper = _CommandWrapper(session, manager=manager)
        self._fs_wrapper = _FileSystemWrapper(session)

    @property
    def command(self) -> BaseExecutor:
        """Get command executor."""
        return self._command_wrapper

    @property
    def fs(self) -> FileSystemBackend:
        """Get filesystem backend."""
        return self._fs_wrapper

    def touch(self) -> None:
        """Update session activity timestamp."""
        self._session.touch()

    def resolve_session_info(self, provider_name: str):
        """Resolve current session info without exposing internal session object."""
        from sandbox.provider import SessionInfo

        instance = self._session.lease.get_instance()
        provider = getattr(self._session.runtime, "provider", None)
        if not instance and provider is not None:
            instance = self._session.lease.ensure_active_instance(provider)
        return SessionInfo(
            session_id=instance.instance_id if instance else "local",
            provider=provider_name,
            status="running",
        )


class _CommandWrapper(BaseExecutor):
    """Wrapper that delegates to runtime's execute method."""

    runtime_owns_cwd = True

    def __init__(self, session: ChatSession, manager: SandboxManager | None = None):
        super().__init__(default_cwd=session.terminal.get_state().cwd)
        self._session = session
        self._manager = manager
        db_path = getattr(session.terminal, "db_path", None)
        self._db_path: Path | None = Path(db_path) if db_path else None

    def _wrap_command(self, command: str, cwd: str | None, env: dict[str, str] | None) -> tuple[str, str]:
        wrapped = command
        if env:
            exports = "\n".join(f"export {k}={shlex.quote(v)}" for k, v in env.items())
            wrapped = f"{exports}\n{wrapped}"
        # @@@runtime-owned-cwd - Preserve runtime session cwd unless caller explicitly requests cwd override.
        work_dir = cwd or self._session.terminal.get_state().cwd
        if cwd:
            wrapped = f"cd {shlex.quote(cwd)}\n{wrapped}"
        return wrapped, work_dir

    async def execute(
        self, command: str, cwd: str | None = None, timeout: float | None = None, env: dict[str, str] | None = None
    ):
        """Execute command via runtime."""
        self._session.touch()
        # @@@command-context - CommandMiddleware passes Cwd/env; preserve that context for remote runtimes.
        wrapped, _ = self._wrap_command(command, cwd, env)
        return await self._session.runtime.execute(wrapped, timeout)

    async def execute_async(self, command: str, cwd: str | None = None, env: dict[str, str] | None = None):
        """Execute command asynchronously via runtime and return command handle."""
        self._session.touch()
        wrapped, work_dir = self._wrap_command(command, cwd, env)
        if self._manager is None:
            return await self._session.runtime.start_command(wrapped, work_dir)
        bg_session = self._manager.create_background_command_session(
            thread_id=self._session.thread_id,
            initial_cwd=work_dir,
        )
        return await bg_session.runtime.start_command(wrapped, work_dir)

    def _lookup_command_terminal_id(self, command_id: str) -> str | None:
        if self._db_path is None:
            return None
        with sqlite3.connect(str(self._db_path), timeout=30) as conn:
            conn.execute("PRAGMA busy_timeout=30000")
            row = conn.execute(
                """
                SELECT tc.terminal_id
                FROM terminal_commands tc
                JOIN abstract_terminals at ON at.terminal_id = tc.terminal_id
                WHERE tc.command_id = ? AND at.thread_id = ?
                """,
                (command_id, self._session.thread_id),
            ).fetchone()
        return str(row[0]) if row else None

    def _load_persisted_command(self, command_id: str) -> sqlite3.Row | None:
        if self._db_path is None:
            return None
        with sqlite3.connect(str(self._db_path), timeout=30) as conn:
            conn.execute("PRAGMA busy_timeout=30000")
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT
                    tc.command_id,
                    tc.command_line,
                    tc.cwd,
                    tc.status,
                    tc.stdout,
                    tc.stderr,
                    tc.exit_code
                FROM terminal_commands tc
                LEFT JOIN abstract_terminals at ON at.terminal_id = tc.terminal_id
                LEFT JOIN chat_sessions cs ON cs.chat_session_id = tc.chat_session_id
                WHERE tc.command_id = ?
                  AND (at.thread_id = ? OR cs.thread_id = ?)
                LIMIT 1
                """,
                (command_id, self._session.thread_id, self._session.thread_id),
            ).fetchone()
        return row

    # @@@persisted-command-fallback - background command terminal/session can be cleaned before command_status; fallback to DB row keeps trace truthful.
    def _command_from_row(self, row: sqlite3.Row) -> AsyncCommand:
        status = str(row["status"] or "")
        return AsyncCommand(
            command_id=str(row["command_id"]),
            command_line=str(row["command_line"] or ""),
            cwd=str(row["cwd"] or ""),
            stdout_buffer=[str(row["stdout"] or "")],
            stderr_buffer=[str(row["stderr"] or "")],
            exit_code=row["exit_code"],
            done=status in {"done", "failed", "cancelled"},
        )

    def _result_from_row(self, row: sqlite3.Row, timeout: float | None = None) -> ExecuteResult:
        status = str(row["status"] or "")
        if status in {"running", "pending"} and timeout is not None and timeout > 0:
            return ExecuteResult(
                exit_code=-1,
                stdout=str(row["stdout"] or ""),
                stderr=str(row["stderr"] or ""),
                timed_out=True,
                command_id=str(row["command_id"]),
            )
        exit_code = row["exit_code"]
        return ExecuteResult(
            exit_code=int(exit_code) if exit_code is not None else 0,
            stdout=str(row["stdout"] or ""),
            stderr=str(row["stderr"] or ""),
            command_id=str(row["command_id"]),
        )

    def _resolve_session_for_terminal(self, terminal_id: str):
        if terminal_id == self._session.terminal.terminal_id:
            return self._session
        if self._manager is None:
            raise RuntimeError(f"Command belongs to terminal {terminal_id}, but manager is unavailable")
        session = self._manager.session_manager.get(self._session.thread_id, terminal_id)
        if session:
            return session
        terminal = self._manager.terminal_store.get_by_id(terminal_id)
        if terminal is None:
            raise RuntimeError(f"Terminal {terminal_id} not found")
        if terminal.thread_id != self._session.thread_id:
            raise RuntimeError(
                f"Terminal {terminal_id} belongs to thread {terminal.thread_id}, not {self._session.thread_id}"
            )
        lease = self._manager.lease_store.get(terminal.lease_id)
        if lease is None:
            raise RuntimeError(f"Lease {terminal.lease_id} not found for terminal {terminal_id}")
        return self._manager.session_manager.create(
            session_id=f"sess-{uuid.uuid4().hex[:12]}",
            thread_id=self._session.thread_id,
            terminal=terminal,
            lease=lease,
        )

    def _resolve_session_for_command(self, command_id: str):
        terminal_id = self._lookup_command_terminal_id(command_id)
        if terminal_id is None:
            if self._manager is None:
                return self._session
            raise RuntimeError(f"Command {command_id} not found for thread {self._session.thread_id}")
        return self._resolve_session_for_terminal(terminal_id)

    async def get_status(self, command_id: str):
        """Get status for an async command."""
        try:
            session = self._resolve_session_for_command(command_id)
            cmd = await session.runtime.get_command(command_id)
            if cmd is not None:
                return cmd
        except RuntimeError:
            pass
        row = self._load_persisted_command(command_id)
        if row is None:
            return None
        return self._command_from_row(row)

    async def wait_for(self, command_id: str, timeout: float | None = None):
        """Wait for async command completion."""
        try:
            session = self._resolve_session_for_command(command_id)
            result = await session.runtime.wait_for_command(command_id, timeout=timeout)
            if result is not None:
                return result
        except RuntimeError:
            pass
        row = self._load_persisted_command(command_id)
        if row is None:
            return None
        return self._result_from_row(row, timeout=timeout)

    def store_completed_result(self, command_id: str, command_line: str, cwd: str, result):
        """Store completed result for command_status lookup."""
        self._session.runtime.store_completed_result(command_id, command_line, cwd, result)


class _FileSystemWrapper(FileSystemBackend):
    """Wrapper that delegates to provider via lease."""

    is_remote = True

    def __init__(self, session: ChatSession):
        self._session = session

    def _get_provider(self):
        """Get provider from session's lease."""
        provider = getattr(self._session.runtime, "provider", None)
        if provider is None:
            raise RuntimeError("FileSystem operations only supported for remote runtimes")
        return provider

    def _get_instance_id(self) -> str:
        """Get active instance ID."""
        # @@@lease-convergence - File operations can also wake paused instances; always converge through lease.
        provider = getattr(self._session.runtime, "provider", None)
        if provider is not None:
            instance = self._session.lease.ensure_active_instance(provider)
        else:
            instance = self._session.lease.get_instance()
            if not instance:
                raise RuntimeError("No active instance")
        return instance.instance_id

    def read_file(self, path: str):
        """Read file via provider."""
        from sandbox.interfaces.filesystem import FileReadResult

        self._session.touch()
        provider = self._get_provider()
        instance_id = self._get_instance_id()

        content = provider.read_file(instance_id, path)
        return FileReadResult(content=content, size=len(content))

    def write_file(self, path: str, content: str):
        """Write file via provider."""
        from sandbox.interfaces.filesystem import FileWriteResult

        self._session.touch()
        provider = self._get_provider()
        instance_id = self._get_instance_id()

        try:
            provider.write_file(instance_id, path, content)
            return FileWriteResult(success=True)
        except Exception as e:
            return FileWriteResult(success=False, error=str(e))

    def file_exists(self, path: str) -> bool:
        """Check if file exists."""
        self._session.touch()
        provider = self._get_provider()
        instance_id = self._get_instance_id()

        try:
            provider.read_file(instance_id, path)
            return True
        except Exception:
            return False

    def file_mtime(self, path: str) -> float | None:
        """Not available for remote sandbox."""
        return None

    def file_size(self, path: str) -> int | None:
        """Not available for remote sandbox."""
        return None

    def is_dir(self, path: str) -> bool:
        """Check if path is directory."""
        self._session.touch()
        provider = self._get_provider()
        instance_id = self._get_instance_id()

        try:
            provider.list_dir(instance_id, path)
            return True
        except Exception:
            return False

    def list_dir(self, path: str):
        """List directory contents."""
        from sandbox.interfaces.filesystem import DirEntry, DirListResult

        self._session.touch()
        provider = self._get_provider()
        instance_id = self._get_instance_id()

        try:
            items = provider.list_dir(instance_id, path)
            entries = []
            for item in items:
                name = item.get("name", "?")
                item_type = item.get("type", "file")
                size = item.get("size", 0)
                entries.append(
                    DirEntry(
                        name=name,
                        is_dir=(item_type == "directory"),
                        size=size,
                    )
                )
            return DirListResult(entries=entries)
        except Exception as e:
            return DirListResult(error=str(e))
