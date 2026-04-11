"""SandboxCapability - Wrapper that hides new architecture from agents.

This module provides the capability object that agents interact with.
It wraps the new architecture (ChatSession → Runtime → Terminal → Lease)
while maintaining the same interface as before.
"""

from __future__ import annotations

import shlex
import uuid
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from sandbox.interfaces.executor import BaseExecutor
from sandbox.interfaces.filesystem import FileSystemBackend
from storage.providers.sqlite.kernel import SQLiteDBRole, connect_sqlite, resolve_role_db_path
from storage.runtime import uses_supabase_runtime_defaults

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
        self._fs_wrapper = _FileSystemWrapper(session, manager=manager)

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

    async def execute(self, command: str, cwd: str | None = None, timeout: float | None = None, env: dict[str, str] | None = None):
        """Execute command via runtime."""
        self._session.touch()
        # @@@command-context - CommandService passes env; preserve that context for remote runtimes.
        wrapped, _ = self._wrap_command(command, cwd, env)
        print(
            "[_CommandWrapper.execute] "
            f"thread_id={self._session.thread_id} "
            f"terminal_id={self._session.terminal.terminal_id} "
            f"command={command[:200]!r} "
            f"cwd={cwd!r} timeout={timeout}",
            flush=True,
        )
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
        command_repo = getattr(self._session, "_session_repo", None)
        if command_repo is not None:
            terminal_id = command_repo.find_command_terminal_id(
                command_id=command_id,
                thread_id=self._session.thread_id,
            )
            if terminal_id is not None:
                return terminal_id
            return None
        if self._db_path is not None and uses_supabase_runtime_defaults() and self._db_path == resolve_role_db_path(SQLiteDBRole.SANDBOX):
            raise RuntimeError("strategy-backed command lookup requires a bound command repo")
        if self._db_path is None:
            return None
        with connect_sqlite(self._db_path) as conn:
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

    def _resolve_session_for_terminal(self, terminal_id: str):
        if terminal_id == self._session.terminal.terminal_id:
            return self._session
        if self._manager is None:
            raise RuntimeError(f"Command belongs to terminal {terminal_id}, but manager is unavailable")
        session = self._manager.session_manager.get(self._session.thread_id, terminal_id)
        if session:
            return session
        terminal_row = self._manager.terminal_store.get_by_id(terminal_id)
        if terminal_row is None:
            raise RuntimeError(f"Terminal {terminal_id} not found")
        from sandbox.terminal import terminal_from_row

        terminal = terminal_from_row(terminal_row, self._manager.db_path)
        if terminal.thread_id != self._session.thread_id:
            raise RuntimeError(f"Terminal {terminal_id} belongs to thread {terminal.thread_id}, not {self._session.thread_id}")
        lease = self._manager.get_lease(terminal.lease_id)
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
        session = self._resolve_session_for_command(command_id)
        return await session.runtime.get_command(command_id)

    async def wait_for(self, command_id: str, timeout: float | None = None):
        """Wait for async command completion."""
        session = self._resolve_session_for_command(command_id)
        return await session.runtime.wait_for_command(command_id, timeout=timeout)


class _FileSystemWrapper(FileSystemBackend):
    """Wrapper that delegates to provider via lease."""

    is_remote = True

    def __init__(self, session: ChatSession, manager: SandboxManager | None = None):
        self._session = session
        self._manager = manager

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
            try:
                instance = self._session.lease.ensure_active_instance(provider)
            except RuntimeError:
                if self._manager is None or getattr(self._session.lease, "observed_state", None) != "paused":
                    raise
                if not self._manager.resume_session(self._session.thread_id, source="auto_resume"):
                    raise
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
        """Best-effort size lookup via parent directory listing."""
        self._session.touch()
        provider = self._get_provider()
        instance_id = self._get_instance_id()

        target = PurePosixPath(path)
        if not target.name:
            return None

        parent = str(target.parent) or "/"
        try:
            entries = provider.list_dir(instance_id, parent)
        except Exception:
            return None

        for entry in entries or []:
            if entry.get("name") != target.name:
                continue
            size = entry.get("size")
            if isinstance(size, int):
                return size
            if isinstance(size, float):
                return int(size)
            return None
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
