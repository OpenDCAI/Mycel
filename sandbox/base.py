"""Sandbox ABC, LocalSandbox, and RemoteSandbox — unified interface for execution environments.

A Sandbox bundles sub-capabilities by interaction surface:
- fs()    → FileSystemBackend  (consumed by FileSystemMiddleware)
- shell() → BaseExecutor       (consumed by CommandMiddleware)
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from sandbox.capability import SandboxCapability
    from sandbox.config import SandboxConfig
    from sandbox.interfaces import BaseExecutor, FileSystemBackend
    from sandbox.manager import SandboxManager
    from sandbox.provider import SandboxProvider


class Sandbox(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def working_dir(self) -> str: ...

    @property
    @abstractmethod
    def env_label(self) -> str: ...

    @abstractmethod
    def fs(self) -> FileSystemBackend | None: ...

    @abstractmethod
    def shell(self) -> BaseExecutor | None: ...

    def close(self) -> None:
        pass


class _LazyFSBackend:
    is_remote = True

    def __init__(self, sandbox: RemoteSandbox):
        self._remote = sandbox

    def __getattr__(self, name: str):
        return getattr(self._remote._get_capability().fs, name)


class _LazyExecutor:
    # @@@lazy-remote-flag - CommandMiddleware probes is_remote during init; keep this side-effect free.
    is_remote = True
    runtime_owns_cwd = True
    # @@@lazy-shell-name - CommandMiddleware logs shell_name during init.
    shell_name = "remote"

    def __init__(self, sandbox: RemoteSandbox):
        self._remote = sandbox

    def __getattr__(self, name: str):
        return getattr(self._remote._get_capability().command, name)


class RemoteSandbox(Sandbox):
    """Concrete sandbox for all provider-backed environments (AgentBay, Docker, E2B, Daytona)."""

    def __init__(
        self,
        provider: SandboxProvider,
        config: SandboxConfig,
        default_cwd: str,
        db_path: Path | None = None,
        *,
        name: str | None = None,
        working_dir: str | None = None,
        env_label: str = "Remote sandbox",
    ) -> None:
        self._config = config
        self._default_cwd = default_cwd
        self._provider = provider
        from sandbox.manager import SandboxManager

        self._manager = SandboxManager(provider=provider, db_path=db_path)
        self._on_exit = config.on_exit
        self._name = name or config.name
        self._working_dir = working_dir or default_cwd
        self._env_label = env_label
        self._capability_cache: dict[str, SandboxCapability] = {}
        self._init_commands_run: set[str] = set()

    def _get_capability(self) -> SandboxCapability:
        from sandbox.thread_context import get_current_thread_id

        thread_id = get_current_thread_id()
        if not thread_id:
            raise RuntimeError("No thread_id set. Call set_current_thread_id first.")
        if thread_id not in self._capability_cache:
            capability = self._manager.get_sandbox(thread_id)
            if self._config.init_commands and thread_id not in self._init_commands_run:
                self._run_init_commands(capability)
                self._init_commands_run.add(thread_id)
            self._capability_cache[thread_id] = capability
        return self._capability_cache[thread_id]

    def _run_init_commands(self, capability: SandboxCapability) -> None:
        for i, cmd in enumerate(self._config.init_commands, 1):
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop:
                future = asyncio.run_coroutine_threadsafe(capability.command.execute(cmd), loop)
                result = future.result(timeout=30)
            else:
                result = asyncio.run(capability.command.execute(cmd))

            if result.exit_code != 0:
                raise RuntimeError(
                    f"Init command #{i} failed: {cmd}\nexit={result.exit_code}\nstderr={result.stderr}\nstdout={result.stdout}"
                )

    def fs(self) -> FileSystemBackend:
        return _LazyFSBackend(self)  # type: ignore[return-value]

    def shell(self) -> BaseExecutor:
        return _LazyExecutor(self)  # type: ignore[return-value]

    @property
    def name(self) -> str:
        return self._name

    @property
    def working_dir(self) -> str:
        return self._working_dir

    @property
    def env_label(self) -> str:
        return self._env_label

    @property
    def manager(self) -> SandboxManager:
        return self._manager

    def ensure_session(self, thread_id: str) -> None:
        from sandbox.thread_context import set_current_thread_id

        set_current_thread_id(thread_id)
        self._capability_cache.pop(thread_id, None)
        self._get_capability()

    def pause_thread(self, thread_id: str) -> bool:
        self._capability_cache.pop(thread_id, None)
        return self._manager.pause_session(thread_id)

    def resume_thread(self, thread_id: str) -> bool:
        self._capability_cache.pop(thread_id, None)
        return self._manager.resume_session(thread_id)

    def close(self) -> None:
        if self._on_exit == "pause":
            try:
                count = self._manager.pause_all_sessions()
                if count > 0:
                    logger.info("[%s] Paused %d session(s)", self.name, count)
            except Exception:
                logger.exception("[%s] pause_all_sessions failed during close", self.name)
        elif self._on_exit == "destroy":
            for session in self._manager.list_sessions():
                try:
                    self._manager.destroy_session(thread_id=session["thread_id"])
                except Exception:
                    logger.exception("[%s] Failed to destroy session %s", self.name, session.get("thread_id"))
            logger.info("[%s] Destroy pass complete", self.name)


class _LazyLocalExecutor:
    is_remote = False
    runtime_owns_cwd = True
    shell_name = "local-session"

    def __init__(self, sandbox: LocalSandbox):
        self._sandbox = sandbox

    def __getattr__(self, name: str):
        return getattr(self._sandbox._get_capability().command, name)


class LocalSandbox(Sandbox):
    """Concrete sandbox for the local host environment."""

    def __init__(self, workspace_root: str, db_path: Path | None = None) -> None:
        from sandbox.manager import SandboxManager
        from sandbox.providers.local import LocalSessionProvider

        self._workspace_root = workspace_root
        self._provider = LocalSessionProvider(default_cwd=workspace_root)
        self._manager = SandboxManager(provider=self._provider, db_path=db_path or (Path.home() / ".leon" / "sandbox.db"))
        self._capability_cache: dict[str, SandboxCapability] = {}

    @property
    def name(self) -> str:
        return "local"

    @property
    def working_dir(self) -> str:
        return self._workspace_root

    @property
    def env_label(self) -> str:
        return "Local host"

    @property
    def manager(self) -> SandboxManager:
        return self._manager

    def _get_capability(self) -> SandboxCapability:
        from sandbox.thread_context import get_current_thread_id

        thread_id = get_current_thread_id()
        if not thread_id:
            raise RuntimeError("No thread_id set. Call set_current_thread_id first.")
        if thread_id not in self._capability_cache:
            self._capability_cache[thread_id] = self._manager.get_sandbox(thread_id)
        return self._capability_cache[thread_id]

    def fs(self) -> FileSystemBackend | None:
        return None

    def shell(self) -> BaseExecutor:
        return _LazyLocalExecutor(self)  # type: ignore[return-value]

    def ensure_session(self, thread_id: str) -> None:
        from sandbox.thread_context import set_current_thread_id

        set_current_thread_id(thread_id)
        self._capability_cache.pop(thread_id, None)
        self._get_capability()

    def pause_thread(self, thread_id: str) -> bool:
        self._capability_cache.pop(thread_id, None)
        return self._manager.pause_session(thread_id)

    def resume_thread(self, thread_id: str) -> bool:
        self._capability_cache.pop(thread_id, None)
        return self._manager.resume_session(thread_id)

    def close(self) -> None:
        for session in self._manager.list_sessions():
            try:
                self._manager.destroy_session(session["thread_id"])
            except Exception:
                logger.exception("[LocalSandbox] Failed to destroy session %s", session.get("thread_id"))
