"""Sandbox session manager.

Orchestrates: Thread → ChatSession → Runtime with sandbox runtime bindings.
"""

import logging
import uuid
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from config.user_paths import user_home_path
from sandbox.capability import SandboxCapability
from sandbox.chat_session import ChatSessionManager, ChatSessionPolicy
from sandbox.clock import parse_runtime_datetime, utc_now
from sandbox.control_plane_repos import make_chat_session_repo, make_sandbox_runtime_repo, make_terminal_repo
from sandbox.provider import SandboxProvider
from sandbox.recipes import bootstrap_recipe
from sandbox.runtime_handle import sandbox_runtime_from_row
from sandbox.terminal import TerminalState, terminal_from_row
from storage.providers.sqlite.kernel import SQLiteDBRole, resolve_role_db_path
from storage.runtime import build_storage_container, uses_supabase_runtime_defaults

logger = logging.getLogger(__name__)


def resolve_provider_cwd(provider) -> str:
    for attr in ("default_cwd", "default_context_path", "mount_path"):
        val = getattr(provider, attr, None)
        if isinstance(val, str) and val:
            return val
    return "/home/user"


def _build_provider_from_name(name: str):
    from backend.sandboxes.service import build_provider_from_config_name

    return build_provider_from_config_name(name)


def lookup_sandbox_for_thread(
    thread_id: str,
    db_path: Path | None = None,
    *,
    terminal_repo: Any | None = None,
    sandbox_runtime_repo: Any | None = None,
) -> str | None:
    target_db = db_path or resolve_role_db_path(SQLiteDBRole.SANDBOX)
    uses_strategy_default_sandbox = uses_supabase_runtime_defaults() and target_db == resolve_role_db_path(SQLiteDBRole.SANDBOX)
    if terminal_repo is None and sandbox_runtime_repo is None and not target_db.exists() and not uses_strategy_default_sandbox:
        return None

    _terminal_repo = terminal_repo
    own_terminal_repo = _terminal_repo is None
    if _terminal_repo is None:
        _terminal_repo = make_terminal_repo(db_path=target_db)
    _sandbox_runtime_repo = sandbox_runtime_repo
    own_sandbox_runtime_repo = _sandbox_runtime_repo is None
    if _sandbox_runtime_repo is None:
        _sandbox_runtime_repo = make_sandbox_runtime_repo(db_path=target_db)
    try:
        terminals = _terminal_repo.list_by_thread(thread_id)
        if not terminals:
            return None
        sandbox_runtime_id = str(terminals[0]["sandbox_runtime_id"])
        sandbox_runtime = _sandbox_runtime_repo.get(sandbox_runtime_id)
        return str(sandbox_runtime["provider_name"]) if sandbox_runtime else None
    finally:
        if own_terminal_repo:
            _terminal_repo.close()
        if own_sandbox_runtime_repo:
            _sandbox_runtime_repo.close()


def resolve_existing_sandbox_runtime_cwd(
    sandbox_runtime_id: str,
    requested_cwd: str | None = None,
    db_path: Path | None = None,
    *,
    sandbox_runtime_repo: Any | None = None,
) -> str:
    if requested_cwd:
        return requested_cwd

    target_db = db_path or resolve_role_db_path(SQLiteDBRole.SANDBOX)
    _sandbox_runtime_repo = sandbox_runtime_repo
    own_sandbox_runtime_repo = _sandbox_runtime_repo is None
    if _sandbox_runtime_repo is None:
        _sandbox_runtime_repo = make_sandbox_runtime_repo(db_path=target_db)
    try:
        sandbox_runtime = _sandbox_runtime_repo.get(sandbox_runtime_id)
    finally:
        if own_sandbox_runtime_repo:
            _sandbox_runtime_repo.close()
    provider_name = str((sandbox_runtime or {}).get("provider_name") or "").strip()
    provider = _build_provider_from_name(provider_name) if provider_name else None
    if provider is not None:
        return resolve_provider_cwd(provider)
    raise ValueError("provider default cwd is required")


def bind_thread_to_existing_sandbox_runtime(
    thread_id: str,
    sandbox_runtime_id: str,
    *,
    cwd: str | None = None,
    db_path: Path | None = None,
    terminal_repo: Any | None = None,
    sandbox_runtime_repo: Any | None = None,
) -> str:
    target_db = db_path or resolve_role_db_path(SQLiteDBRole.SANDBOX)
    _terminal_repo = terminal_repo
    own_terminal_repo = _terminal_repo is None
    if _terminal_repo is None:
        _terminal_repo = make_terminal_repo(db_path=target_db)
    try:
        existing = _terminal_repo.get_active(thread_id)
        if existing is not None:
            return str(existing["cwd"])
        initial_cwd = resolve_existing_sandbox_runtime_cwd(
            sandbox_runtime_id,
            cwd,
            db_path=target_db,
            sandbox_runtime_repo=sandbox_runtime_repo,
        )
        _terminal_repo.create(
            terminal_id=f"term-{uuid.uuid4().hex[:12]}",
            thread_id=thread_id,
            sandbox_runtime_id=sandbox_runtime_id,
            initial_cwd=initial_cwd,
        )
        return initial_cwd
    finally:
        if own_terminal_repo:
            _terminal_repo.close()


def resolve_existing_sandbox_runtime(
    sandbox: Any,
    *,
    db_path: Path | None = None,
    sandbox_runtime_repo: Any | None = None,
) -> dict[str, Any] | None:
    provider_name = str(
        (sandbox.get("provider_name") if isinstance(sandbox, dict) else getattr(sandbox, "provider_name", None)) or ""
    ).strip()
    provider_env_id = str(
        (sandbox.get("provider_env_id") if isinstance(sandbox, dict) else getattr(sandbox, "provider_env_id", None)) or ""
    ).strip()
    if not provider_name:
        raise RuntimeError("sandbox.provider_name is required")
    if not provider_env_id:
        raise RuntimeError("sandbox.provider_env_id is required")

    # @@@existing-sandbox-runtime-identity - existing-sandbox reuse must bind
    # through live runtime identity; stored runtime config is not a resolution source.
    target_db = db_path or resolve_role_db_path(SQLiteDBRole.SANDBOX)
    _sandbox_runtime_repo = sandbox_runtime_repo
    own_sandbox_runtime_repo = _sandbox_runtime_repo is None
    if _sandbox_runtime_repo is None:
        _sandbox_runtime_repo = make_sandbox_runtime_repo(db_path=target_db)
    try:
        sandbox_runtime = _sandbox_runtime_repo.find_by_instance(provider_name=provider_name, instance_id=provider_env_id)
        if sandbox_runtime is not None:
            return sandbox_runtime
    finally:
        if own_sandbox_runtime_repo:
            _sandbox_runtime_repo.close()
    raise RuntimeError("sandbox provider_env_id did not resolve to a sandbox runtime")


def bind_thread_to_existing_sandbox(
    thread_id: str,
    sandbox: Any,
    *,
    cwd: str | None = None,
    db_path: Path | None = None,
    terminal_repo: Any | None = None,
    sandbox_runtime_repo: Any | None = None,
) -> tuple[str, dict[str, Any]]:
    sandbox_runtime = resolve_existing_sandbox_runtime(
        sandbox,
        db_path=db_path,
        sandbox_runtime_repo=sandbox_runtime_repo,
    )
    if sandbox_runtime is None:
        raise RuntimeError("sandbox provider_env_id did not resolve to a sandbox runtime")
    sandbox_runtime_id = str(sandbox_runtime.get("sandbox_runtime_id") or "").strip()
    if not sandbox_runtime_id:
        raise RuntimeError("sandbox_runtime.sandbox_runtime_id is required")
    initial_cwd = bind_thread_to_existing_sandbox_runtime(
        thread_id,
        sandbox_runtime_id,
        cwd=cwd,
        db_path=db_path,
        terminal_repo=terminal_repo,
        sandbox_runtime_repo=sandbox_runtime_repo,
    )
    return initial_cwd, sandbox_runtime


def bind_thread_to_existing_thread_sandbox_runtime(
    thread_id: str,
    source_thread_id: str,
    *,
    cwd: str | None = None,
    db_path: Path | None = None,
    terminal_repo: Any | None = None,
    sandbox_runtime_repo: Any | None = None,
) -> str | None:
    target_db = db_path or resolve_role_db_path(SQLiteDBRole.SANDBOX)
    if not cwd:
        raise ValueError("thread reuse cwd is required")
    _terminal_repo = terminal_repo
    own_terminal_repo = _terminal_repo is None
    if _terminal_repo is None:
        _terminal_repo = make_terminal_repo(db_path=target_db)
    try:
        source_terminal = _terminal_repo.get_active(source_thread_id)
    finally:
        if own_terminal_repo:
            _terminal_repo.close()
    if source_terminal is None:
        return None
    # @@@subagent-runtime-reuse
    # Child threads need their own terminal/session state while reusing the
    # parent's sandbox runtime binding instead of silently provisioning a new one.
    return bind_thread_to_existing_sandbox_runtime(
        thread_id,
        str(source_terminal["sandbox_runtime_id"]),
        cwd=cwd,
        db_path=target_db,
        terminal_repo=terminal_repo,
        sandbox_runtime_repo=sandbox_runtime_repo,
    )


class SandboxManager:
    def __init__(
        self,
        provider: SandboxProvider,
        db_path: Path | None = None,
        on_session_ready: Callable[[str, str], None] | None = None,
    ):
        self.provider = provider
        self.provider_capability = provider.get_capability()
        self._on_session_ready = on_session_ready

        self.db_path = db_path or resolve_role_db_path(SQLiteDBRole.SANDBOX)
        self.terminal_store = make_terminal_repo(db_path=self.db_path)
        self.sandbox_runtime_store = make_sandbox_runtime_repo(db_path=self.db_path)

        self.session_manager = ChatSessionManager(
            provider=provider,
            db_path=self.db_path,
            default_policy=ChatSessionPolicy(),
            chat_session_repo=make_chat_session_repo(db_path=self.db_path),
            terminal_repo=self.terminal_store,
            sandbox_runtime_repo=self.sandbox_runtime_store,
        )

        from sandbox.volume import SandboxVolume

        self.volume = SandboxVolume(
            provider=provider,
            provider_capability=self.provider_capability,
        )

    def _get_sandbox_runtime(self, sandbox_runtime_id: str):
        """Get sandbox runtime as domain object, or None."""
        row = self.sandbox_runtime_store.get(sandbox_runtime_id)
        if row is None:
            return None
        return sandbox_runtime_from_row(row, self.db_path)

    def _create_sandbox_runtime(self, sandbox_runtime_id: str, provider_name: str):
        """Create sandbox runtime and return as domain object."""
        row = self.sandbox_runtime_store.create(sandbox_runtime_id, provider_name)
        return sandbox_runtime_from_row(row, self.db_path)

    def get_terminal(self, thread_id: str):
        """Public API: get active terminal as domain object."""
        return self._get_active_terminal(thread_id)

    def get_sandbox_runtime(self, sandbox_runtime_id: str):
        """Public API: get sandbox runtime as domain object."""
        return self._get_sandbox_runtime(sandbox_runtime_id)

    def _default_terminal_cwd(self) -> str:
        return resolve_provider_cwd(self.provider)

    def _requires_volume_bootstrap(self) -> bool:
        # @@@local-shell-no-volume-gate - local runtimes execute directly on the host
        # and should not fail to start a shell just because remote file-channel
        # bootstrap is irrelevant for that runtime kind.
        return self.provider_capability.runtime_kind != "local"

    def _destroy_daytona_managed_volume(self, sandbox_runtime_id: str) -> None:
        self.provider.delete_managed_volume(f"leon-volume-{sandbox_runtime_id}")

    def _setup_mounts(self, thread_id: str) -> dict:
        """Mount the workspace file channel into the sandbox."""
        terminal = self._get_active_terminal(thread_id)
        if not terminal:
            raise ValueError(f"No active terminal for thread {thread_id}")
        sandbox_runtime = self._get_sandbox_runtime(terminal.sandbox_runtime_id)
        if not sandbox_runtime:
            raise ValueError(f"No sandbox runtime for thread {thread_id}")
        remote_path = self.volume.resolve_mount_path()
        source_path = self._resolve_sync_source_path(thread_id)

        if self.provider_capability.runtime_kind != "daytona_pty":
            self.volume.mount(thread_id, source_path, remote_path)
            return {"source_path": source_path, "remote_path": remote_path}

        # @@@daytona-upgrade - first startup creates managed volume
        volume_name = self._upgrade_to_daytona_volume(
            thread_id,
            sandbox_runtime.sandbox_runtime_id,
            remote_path,
        )
        self.volume.mount_managed_volume(thread_id, volume_name, remote_path)

        return {"source_path": source_path, "remote_path": remote_path}

    def _upgrade_to_daytona_volume(self, thread_id: str, sandbox_runtime_id: str, remote_path: str):
        """Ensure Daytona managed volume exists and return provider backend ref."""

        try:
            volume_name = self.provider.create_managed_volume(sandbox_runtime_id, remote_path)
        except Exception as e:
            if "already exists" in str(e):
                volume_name = f"leon-volume-{sandbox_runtime_id}"
                logger.info("Daytona volume already exists: %s, reusing", volume_name)
                self.provider.wait_managed_volume_ready(volume_name)
            else:
                raise

        return volume_name

    def _fire_session_ready(self, session_id: str, reason: str) -> None:
        if self._on_session_ready:
            self._on_session_ready(session_id, reason)

    def _ensure_sandbox_runtime_bound_instance(self, sandbox_runtime) -> None:
        if self.provider_capability.eager_instance_binding and not sandbox_runtime.get_instance():
            sandbox_runtime.ensure_active_instance(self.provider)

    def _assert_sandbox_runtime_provider(self, sandbox_runtime, thread_id: str) -> None:
        if sandbox_runtime.provider_name != self.provider.name:
            raise RuntimeError(
                f"Thread {thread_id} is bound to provider {sandbox_runtime.provider_name}, "
                f"but current manager provider is {self.provider.name}. "
                "Use the matching sandbox type for this thread or recreate the thread."
            )

    def _get_active_terminal(self, thread_id: str):
        row = self.terminal_store.get_active(thread_id)
        if row:
            return terminal_from_row(row, self.db_path)
        thread_terminals = self.terminal_store.list_by_thread(thread_id)
        # @@@thread-pointer-consistency - If terminals exist but no active pointer, DB is inconsistent and must fail loudly.
        if thread_terminals:
            raise RuntimeError(f"Thread {thread_id} has terminals but no active terminal pointer")
        return None

    def _get_thread_terminals(self, thread_id: str):
        rows = self.terminal_store.list_by_thread(thread_id)
        return [terminal_from_row(row, self.db_path) for row in rows]

    def _get_thread_sandbox_runtime(self, thread_id: str):
        terminals = self._get_thread_terminals(thread_id)
        if not terminals:
            return None
        sandbox_runtime_ids = {terminal.sandbox_runtime_id for terminal in terminals}
        # @@@thread-single-runtime-invariant - Terminals created via non-block must share one sandbox runtime per thread.
        if len(sandbox_runtime_ids) != 1:
            raise RuntimeError(f"Thread {thread_id} has inconsistent sandbox_runtime_ids: {sorted(sandbox_runtime_ids)}")
        sandbox_runtime_id = next(iter(sandbox_runtime_ids))
        sandbox_runtime = self._get_sandbox_runtime(sandbox_runtime_id)
        if sandbox_runtime is None:
            return None
        self._assert_sandbox_runtime_provider(sandbox_runtime, thread_id)
        return sandbox_runtime

    def _thread_belongs_to_provider(self, thread_id: str) -> bool:
        terminals = self._get_thread_terminals(thread_id)
        if not terminals:
            return False
        sandbox_runtime = self._get_sandbox_runtime(terminals[0].sandbox_runtime_id)
        return bool(sandbox_runtime and sandbox_runtime.provider_name == self.provider.name)

    def _resolve_sync_source_path(self, thread_id: str) -> Path:
        container = build_storage_container()
        thread_repo = container.thread_repo()
        try:
            thread_row = thread_repo.get_by_id(thread_id)
        finally:
            close = getattr(thread_repo, "close", None)
            if callable(close):
                close()
        if thread_row is None:
            raise ValueError(f"Thread not found: {thread_id}")
        workspace_id = (
            thread_row.get("current_workspace_id") if isinstance(thread_row, dict) else getattr(thread_row, "current_workspace_id", None)
        )
        if not workspace_id:
            raise ValueError("thread.current_workspace_id is required")
        return user_home_path("file_channels", str(workspace_id)).expanduser().resolve()

    def _skip_volume_sync_for_local_sandbox_runtime(self, sandbox_runtime) -> bool:
        # @@@local-no-volume-sync - local sessions execute directly in host cwd, so upload/download
        # must always no-op there rather than reactivating volume-backed sync.
        return sandbox_runtime is not None and not self._requires_volume_bootstrap()

    def _sync_to_sandbox(self, thread_id: str, instance_id: str, source=None, files: list[str] | None = None) -> None:
        if source is None:
            sandbox_runtime = self._get_thread_sandbox_runtime(thread_id)
            if self._skip_volume_sync_for_local_sandbox_runtime(sandbox_runtime):
                return
            source = self._resolve_sync_source_path(thread_id)
        self.volume.sync_upload(thread_id, instance_id, source, self.volume.resolve_mount_path(), files=files)

    def _sync_from_sandbox(self, thread_id: str, instance_id: str, source=None) -> None:
        if source is None:
            sandbox_runtime = self._get_thread_sandbox_runtime(thread_id)
            if self._skip_volume_sync_for_local_sandbox_runtime(sandbox_runtime):
                return
            source = self._resolve_sync_source_path(thread_id)
        self.volume.sync_download(thread_id, instance_id, source, self.volume.resolve_mount_path())

    def sync_uploads(self, thread_id: str, files: list[str] | None = None) -> bool:
        """Upload files to the active sandbox. Returns False if no active session."""
        terminal = self._get_active_terminal(thread_id)
        if not terminal:
            return False
        session = self.session_manager.get(thread_id, terminal.terminal_id)
        if not session:
            return False
        instance = session.sandbox_runtime.get_instance()
        if not instance:
            return False
        self._sync_to_sandbox(thread_id, instance.instance_id, files=files)
        return True

    def close(self):
        self.session_manager.close(reason="manager_close")
        self.terminal_store.close()
        self.sandbox_runtime_store.close()

    def get_sandbox(self, thread_id: str, bind_mounts: list | None = None) -> SandboxCapability:
        from sandbox.thread_context import set_current_thread_id

        set_current_thread_id(thread_id)

        terminal = self._get_active_terminal(thread_id)
        session = self.session_manager.get(thread_id, terminal.terminal_id) if terminal else None
        if session:
            self._assert_sandbox_runtime_provider(session.sandbox_runtime, thread_id)
            # @@@activity-resume - Any new activity against a paused thread must resume before command execution.
            if session.status == "paused" or getattr(session.sandbox_runtime, "observed_state", None) == "paused":
                if not self.resume_session(thread_id, source="auto_resume"):
                    raise RuntimeError(f"Failed to resume paused session for thread {thread_id}")
                session = self.session_manager.get(thread_id, session.terminal.terminal_id)
                if not session:
                    raise RuntimeError(f"Session disappeared after resume for thread {thread_id}")
                self._assert_sandbox_runtime_provider(session.sandbox_runtime, thread_id)
            # Stamp bind_mounts on provider thread state so lazy create_session paths pick them up
            if bind_mounts:
                self.provider.set_thread_bind_mounts(thread_id, bind_mounts)
            self._ensure_sandbox_runtime_bound_instance(session.sandbox_runtime)
            return SandboxCapability(session, manager=self)

        if not terminal:
            terminal_id = f"term-{uuid.uuid4().hex[:12]}"
            sandbox_runtime_id = f"runtime-{uuid.uuid4().hex[:12]}"
            sandbox_runtime = self._create_sandbox_runtime(sandbox_runtime_id, self.provider.name)
            initial_cwd = self._default_terminal_cwd()
            terminal = terminal_from_row(
                self.terminal_store.create(
                    terminal_id=terminal_id,
                    thread_id=thread_id,
                    sandbox_runtime_id=sandbox_runtime_id,
                    initial_cwd=initial_cwd,
                ),
                self.db_path,
            )
        else:
            sandbox_runtime = self._get_sandbox_runtime(terminal.sandbox_runtime_id)
            if not sandbox_runtime:
                sandbox_runtime = self._create_sandbox_runtime(terminal.sandbox_runtime_id, self.provider.name)
            self._assert_sandbox_runtime_provider(sandbox_runtime, thread_id)
            if sandbox_runtime.observed_state == "paused":
                # @@@paused-runtime-rehydrate - a persisted thread can lose its in-memory chat session
                # while the sandbox runtime stays paused in storage; resume before reconstructing capability.
                if not self.resume_session(thread_id, source="auto_resume"):
                    raise RuntimeError(f"Failed to resume paused session for thread {thread_id}")
                session = self.session_manager.get(thread_id, terminal.terminal_id)
                if session:
                    self._assert_sandbox_runtime_provider(session.sandbox_runtime, thread_id)
                    self._ensure_sandbox_runtime_bound_instance(session.sandbox_runtime)
                    return SandboxCapability(session, manager=self)
                sandbox_runtime = self._get_sandbox_runtime(terminal.sandbox_runtime_id)
                if not sandbox_runtime:
                    raise RuntimeError(f"Sandbox runtime disappeared after resume for thread {thread_id}")
                self._assert_sandbox_runtime_provider(sandbox_runtime, thread_id)

        # Stamp bind_mounts on provider thread state so lazy create_session paths pick them up
        if bind_mounts:
            self.provider.set_thread_bind_mounts(thread_id, bind_mounts)

        storage = None
        if self._requires_volume_bootstrap():
            # @@@volume-strategy-gate - remote runtimes need volume mount/sync before first command.
            storage = self._setup_mounts(thread_id)

        self._ensure_sandbox_runtime_bound_instance(sandbox_runtime)

        # @@@force-instance-for-sync - Non-eager providers (E2B, Daytona, etc.) create instances lazily.
        # Force instance creation here so workspace sync can upload files before tools run.
        if not sandbox_runtime.get_instance():
            sandbox_runtime.ensure_active_instance(self.provider)

        instance = sandbox_runtime.get_instance()
        if instance:
            recipe_env = bootstrap_recipe(self.provider, session_id=instance.instance_id, recipe=sandbox_runtime.recipe)
            if recipe_env:
                terminal_state = terminal.get_state()
                terminal.update_state(
                    TerminalState(
                        cwd=terminal_state.cwd,
                        env_delta={**terminal_state.env_delta, **recipe_env},
                        state_version=terminal_state.state_version,
                    )
                )

        session_id = f"sess-{uuid.uuid4().hex[:12]}"
        session = self.session_manager.create(
            session_id=session_id,
            thread_id=thread_id,
            terminal=terminal,
            sandbox_runtime=sandbox_runtime,
        )

        if instance and storage is not None:
            # @@@workspace-upload - sync files to sandbox after creation
            self._sync_to_sandbox(thread_id, instance.instance_id, source=storage["source_path"])
            self._fire_session_ready(instance.instance_id, "create")

        return SandboxCapability(session, manager=self)

    def create_background_command_session(self, thread_id: str, initial_cwd: str) -> Any:
        default_row = self.terminal_store.get_default(thread_id)
        if default_row is None:
            raise RuntimeError(f"Thread {thread_id} has no default terminal")
        default_terminal = terminal_from_row(default_row, self.db_path)
        sandbox_runtime = self._get_sandbox_runtime(default_terminal.sandbox_runtime_id)
        if sandbox_runtime is None:
            raise RuntimeError(f"Missing sandbox runtime {default_terminal.sandbox_runtime_id} for thread {thread_id}")
        self._assert_sandbox_runtime_provider(sandbox_runtime, thread_id)

        inherited = default_terminal.get_state()
        terminal_id = f"term-{uuid.uuid4().hex[:12]}"
        terminal = terminal_from_row(
            self.terminal_store.create(
                terminal_id=terminal_id,
                thread_id=thread_id,
                sandbox_runtime_id=sandbox_runtime.sandbox_runtime_id,
                initial_cwd=initial_cwd,
            ),
            self.db_path,
        )
        # @@@async-terminal-inherit-state - non-blocking commands fork from default terminal cwd/env snapshot.
        terminal.update_state(
            TerminalState(
                cwd=initial_cwd,
                env_delta=dict(inherited.env_delta),
                state_version=inherited.state_version,
            )
        )
        return self.session_manager.create(
            session_id=f"sess-{uuid.uuid4().hex[:12]}",
            thread_id=thread_id,
            terminal=terminal,
            sandbox_runtime=sandbox_runtime,
        )

    def _terminal_is_busy(self, terminal_id: str) -> bool:
        if not terminal_id:
            return False
        if not self.db_path.exists():
            return False
        return self.session_manager._repo.terminal_has_running_command(terminal_id)

    def _sandbox_runtime_is_busy(self, sandbox_runtime_id: str) -> bool:
        if not sandbox_runtime_id:
            return False
        if not self.db_path.exists():
            return False
        return self.session_manager._repo.sandbox_runtime_has_running_command(sandbox_runtime_id)

    def _is_expired(self, session_row: dict, now: datetime) -> bool:
        started_at_raw = session_row.get("started_at")
        last_active_raw = session_row.get("last_active_at")
        if not started_at_raw or not last_active_raw:
            return False
        started_at = parse_runtime_datetime(str(started_at_raw))
        last_active_at = parse_runtime_datetime(str(last_active_raw))
        idle_ttl_sec = int(session_row.get("idle_ttl_sec") or 0)
        max_duration_sec = int(session_row.get("max_duration_sec") or 0)
        idle_elapsed = (now - last_active_at).total_seconds()
        total_elapsed = (now - started_at).total_seconds()
        return idle_elapsed > idle_ttl_sec or total_elapsed > max_duration_sec

    def enforce_idle_timeouts(self) -> int:
        """Pause expired sandbox runtimes and close chat sessions.

        Rule:
        - If a chat session is idle past idle_ttl_sec, or older than max_duration_sec:
          1) pause physical sandbox runtime instance (remote providers)
          2) close chat session runtime + mark session closed
        - Local sandbox is exempt from idle timeout (no cost to keep running)
        """
        if self.provider.name == "local":
            return 0

        now = utc_now()
        count = 0

        active_rows = self.session_manager.list_active()

        for row in active_rows:
            session_id = row.get("session_id")
            thread_id = row.get("thread_id")
            started_at_raw = row.get("started_at")
            last_active_raw = row.get("last_active_at")
            if not session_id or not thread_id or not started_at_raw or not last_active_raw:
                continue

            started_at = parse_runtime_datetime(str(started_at_raw))
            last_active_at = parse_runtime_datetime(str(last_active_raw))
            idle_ttl_sec = int(row.get("idle_ttl_sec") or 0)
            max_duration_sec = int(row.get("max_duration_sec") or 0)

            idle_elapsed = (now - last_active_at).total_seconds()
            total_elapsed = (now - started_at).total_seconds()
            if idle_elapsed <= idle_ttl_sec and total_elapsed <= max_duration_sec:
                continue

            terminal_id = row.get("terminal_id")
            terminal_row = self.terminal_store.get_by_id(str(terminal_id)) if terminal_id else None
            terminal = terminal_from_row(terminal_row, self.db_path) if terminal_row else None
            sandbox_runtime = self._get_sandbox_runtime(terminal.sandbox_runtime_id) if terminal else None
            if sandbox_runtime and sandbox_runtime.provider_name != self.provider.name:
                continue

            if terminal and self._terminal_is_busy(terminal.terminal_id):
                continue

            if sandbox_runtime:
                # @@@idle-reaper-shared-runtime - non-blocking commands fork background terminals but share one sandbox runtime.
                # Do not pause the underlying sandbox runtime if another session on the same runtime is still active/idle.
                sandbox_runtime_id = str(row.get("sandbox_runtime_id") or "")
                if not sandbox_runtime_id:
                    continue
                has_other_active = False
                for other in active_rows:
                    if str(other.get("sandbox_runtime_id") or "") != sandbox_runtime_id:
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
                    if self._sandbox_runtime_is_busy(sandbox_runtime.sandbox_runtime_id):
                        continue
                    status = sandbox_runtime.refresh_instance_status(self.provider)
                    capability = self.provider.get_capability()
                    # @@@idle-reaper-reclaim-contract - idle timeout must reclaim remote resources; providers
                    # that cannot pause should destroy instead of repeatedly throwing unsupported-operation noise.
                    if status == "running" and self.provider.name != "local":
                        try:
                            if capability.can_pause:
                                reclaimed = sandbox_runtime.pause_instance(self.provider, source="idle_reaper")
                            elif capability.can_destroy:
                                reclaimed = sandbox_runtime.destroy_instance(self.provider, source="idle_reaper") is None
                            else:
                                print(
                                    f"[idle-reaper] provider {self.provider.name} cannot reclaim expired sandbox runtime "
                                    f"{sandbox_runtime.sandbox_runtime_id} for thread {thread_id}"
                                )
                                continue
                        except Exception as exc:
                            print(
                                "[idle-reaper] failed to reclaim expired sandbox runtime "
                                f"{sandbox_runtime.sandbox_runtime_id} for thread {thread_id}: {exc}"
                            )
                            continue
                        if not reclaimed:
                            print(
                                "[idle-reaper] failed to reclaim expired sandbox runtime "
                                f"{sandbox_runtime.sandbox_runtime_id} for thread {thread_id}"
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

        sandbox_runtime = self._get_thread_sandbox_runtime(thread_id)
        if not sandbox_runtime:
            return False

        if sandbox_runtime.observed_state != "paused":
            # @@@pause-rebind-instance - Pause must operate on a concrete running instance.
            # Re-resolve through sandbox runtime to avoid pausing stale detached bindings.
            sandbox_runtime.ensure_active_instance(self.provider)
            instance = sandbox_runtime.get_instance()
            if instance:
                # @@@workspace-download - sync files from sandbox before pause
                try:
                    self._sync_from_sandbox(thread_id, instance.instance_id)
                except Exception:
                    logger.error("Failed to download workspace before pause — agent changes may be lost", exc_info=True)
                    raise
            if not sandbox_runtime.pause_instance(self.provider, source="user_pause"):
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

    def resume_session(self, thread_id: str, source: str = "user_resume") -> bool:
        terminals = self._get_thread_terminals(thread_id)
        if not terminals:
            return False

        sandbox_runtime = self._get_thread_sandbox_runtime(thread_id)
        if not sandbox_runtime:
            return False

        if not sandbox_runtime.resume_instance(self.provider, source=source):
            return False

        # @@@workspace-upload-on-resume - re-sync files that may have been uploaded while paused
        instance = sandbox_runtime.get_instance()
        if instance:
            self._sync_to_sandbox(thread_id, instance.instance_id)

        resumed_any = False
        for terminal in terminals:
            session = self.session_manager.get(thread_id, terminal.terminal_id)
            if session:
                session.sandbox_runtime = sandbox_runtime
                runtime = getattr(session, "runtime", None)
                if runtime is not None:
                    runtime.sandbox_runtime = sandbox_runtime
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
                raise RuntimeError(f"Session {session_id} belongs to thread {matched_thread_id}, not thread {thread_id}")

        terminals = self._get_thread_terminals(thread_id)
        if not terminals:
            return False

        return self.destroy_thread_resources(thread_id)

    def destroy_thread_resources(self, thread_id: str) -> bool:
        """Destroy physical resources and detach thread from terminal/runtime records."""
        terminal_rows = self.terminal_store.list_by_thread(thread_id)
        terminals = [terminal_from_row(r, self.db_path) for r in terminal_rows]
        if not terminals:
            return False

        # @@@workspace-download-before-destroy - sync files before destroy
        sandbox_runtime = self._get_thread_sandbox_runtime(thread_id)
        if sandbox_runtime and sandbox_runtime.observed_state == "running":
            instance = sandbox_runtime.get_instance()
            if instance:
                try:
                    self._sync_from_sandbox(thread_id, instance.instance_id)
                except Exception:
                    logger.error("Failed to download workspace before destroy — agent changes are lost", exc_info=True)
                    raise
        self.volume.clear_sync_state(thread_id)

        sandbox_runtime_ids = {terminal.sandbox_runtime_id for terminal in terminals}

        self.session_manager.delete_thread(thread_id, reason="thread_deleted")

        for terminal in terminals:
            self.terminal_store.delete(terminal.terminal_id)

        for sandbox_runtime_id in sandbox_runtime_ids:
            # @@@shared-runtime-destroy-boundary - destroying one thread must not tear down
            # a sandbox runtime that still has surviving terminals bound to it.
            sandbox_runtime_in_use = any(row.get("sandbox_runtime_id") == sandbox_runtime_id for row in self.terminal_store.list_all())
            if sandbox_runtime_in_use:
                continue
            if not self.destroy_sandbox_runtime_resources(sandbox_runtime_id):
                raise RuntimeError(f"Missing sandbox runtime {sandbox_runtime_id} for thread {thread_id}")
        return True

    def destroy_sandbox_runtime_resources(self, sandbox_runtime_id: str) -> bool:
        sandbox_runtime = self._get_sandbox_runtime(sandbox_runtime_id)
        if not sandbox_runtime:
            return False
        if any(row.get("sandbox_runtime_id") == sandbox_runtime_id for row in self.terminal_store.list_all()):
            raise RuntimeError(f"Sandbox runtime {sandbox_runtime_id} still has bound terminals")
        sandbox_runtime.destroy_instance(self.provider)
        if self.provider_capability.runtime_kind == "daytona_pty":
            self._destroy_daytona_managed_volume(sandbox_runtime_id)
        self.sandbox_runtime_store.delete(sandbox_runtime_id)
        return True

    def list_sessions(self) -> list[dict]:
        sessions: list[dict] = []

        terminals = self.terminal_store.list_all()
        threads_by_runtime: dict[str, list[str]] = {}
        for term in terminals:
            sandbox_runtime_id = term.get("sandbox_runtime_id")
            thread_id = term.get("thread_id")
            if sandbox_runtime_id and thread_id:
                threads_by_runtime.setdefault(sandbox_runtime_id, []).append(thread_id)

        rows = self.session_manager.list_all()
        active_rows = [r for r in rows if r.get("status") in {"active", "idle", "paused"}]
        chat_by_thread_runtime: dict[tuple[str, str], dict] = {}
        for row in active_rows:
            thread_id = row.get("thread_id")
            sandbox_runtime_id = row.get("sandbox_runtime_id")
            if not thread_id or not sandbox_runtime_id:
                continue
            key = (str(thread_id), str(sandbox_runtime_id))
            if key not in chat_by_thread_runtime:
                chat_by_thread_runtime[key] = row
        inspect_visible = self.provider_capability.inspect_visible

        seen_instance_ids: set[str] = set()

        for sandbox_runtime_row in self.sandbox_runtime_store.list_by_provider(self.provider.name):
            sandbox_runtime_id = sandbox_runtime_row["sandbox_runtime_id"]
            sandbox_runtime = self._get_sandbox_runtime(sandbox_runtime_id)
            if not sandbox_runtime:
                continue

            instance = sandbox_runtime.get_instance()
            if not instance:
                continue

            status = sandbox_runtime.refresh_instance_status(self.provider)
            refreshed_instance = sandbox_runtime.get_instance()
            if not refreshed_instance or status in {"detached", "deleted", "stopped", "dead"}:
                continue

            seen_instance_ids.add(refreshed_instance.instance_id)
            threads = sorted(set(threads_by_runtime.get(sandbox_runtime_id) or []))

            if not threads:
                sessions.append(
                    {
                        "session_id": refreshed_instance.instance_id,
                        "thread_id": "(untracked)",
                        "provider": self.provider.name,
                        "status": status,
                        "created_at": sandbox_runtime_row.get("created_at"),
                        "last_active": sandbox_runtime_row.get("updated_at"),
                        "sandbox_runtime_id": sandbox_runtime_id,
                        "instance_id": refreshed_instance.instance_id,
                        "chat_session_id": None,
                        "source": "runtime",
                        "inspect_visible": inspect_visible,
                    }
                )
                continue

            for thread_id in threads:
                chat = chat_by_thread_runtime.get((thread_id, sandbox_runtime_id))
                sessions.append(
                    {
                        "session_id": refreshed_instance.instance_id,
                        "thread_id": thread_id,
                        "provider": self.provider.name,
                        "status": status,
                        "created_at": sandbox_runtime_row.get("created_at"),
                        "last_active": (chat or {}).get("last_active_at") or sandbox_runtime_row.get("updated_at"),
                        "sandbox_runtime_id": sandbox_runtime_id,
                        "instance_id": refreshed_instance.instance_id,
                        "chat_session_id": (chat or {}).get("session_id"),
                        "source": "runtime",
                        "inspect_visible": inspect_visible,
                    }
                )

        list_provider_runtimes = getattr(self.provider, "list_provider_runtimes", None)
        provider_runtimes = []
        if callable(list_provider_runtimes):
            raw_provider_runtimes = list_provider_runtimes()
            if not isinstance(raw_provider_runtimes, list):
                raise TypeError(f"{self.provider.name}.list_provider_runtimes must return list")
            provider_runtimes = raw_provider_runtimes

        for ps in provider_runtimes:
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
                    "instance_id": instance_id,
                    "chat_session_id": None,
                    "source": "provider_orphan",
                    "inspect_visible": inspect_visible,
                }
            )

        return sessions
