"""Sandbox session manager.

Orchestrates: Thread → ChatSession → Runtime → Terminal → Lease → Instance
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
from sandbox.control_plane_repos import make_chat_session_repo, make_lease_repo, make_terminal_repo
from sandbox.lease import lease_from_row
from sandbox.provider import SandboxProvider
from sandbox.recipes import bootstrap_recipe
from sandbox.terminal import TerminalState, terminal_from_row
from storage.providers.sqlite.kernel import SQLiteDBRole, resolve_role_db_path
from storage.runtime import build_storage_container, uses_supabase_runtime_defaults

logger = logging.getLogger(__name__)


def resolve_provider_cwd(provider) -> str:
    """Get the default working directory for a provider."""
    for attr in ("default_cwd", "default_context_path", "mount_path"):
        val = getattr(provider, attr, None)
        if isinstance(val, str) and val:
            return val
    return "/home/user"


def _build_provider_from_name(name: str):
    from backend.web.services.sandbox_service import build_provider_from_config_name

    return build_provider_from_config_name(name)


def lookup_sandbox_for_thread(
    thread_id: str,
    db_path: Path | None = None,
    *,
    terminal_repo: Any | None = None,
    lease_repo: Any | None = None,
) -> str | None:
    target_db = db_path or resolve_role_db_path(SQLiteDBRole.SANDBOX)
    uses_strategy_default_sandbox = uses_supabase_runtime_defaults() and target_db == resolve_role_db_path(SQLiteDBRole.SANDBOX)
    if terminal_repo is None and lease_repo is None and not target_db.exists() and not uses_strategy_default_sandbox:
        return None

    _terminal_repo = terminal_repo
    own_terminal_repo = _terminal_repo is None
    if _terminal_repo is None:
        _terminal_repo = make_terminal_repo(db_path=target_db)
    _lease_repo = lease_repo
    own_lease_repo = _lease_repo is None
    if _lease_repo is None:
        _lease_repo = make_lease_repo(db_path=target_db)
    try:
        terminals = _terminal_repo.list_by_thread(thread_id)
        if not terminals:
            return None
        lease_id = str(terminals[0]["lease_id"])
        lease = _lease_repo.get(lease_id)
        return str(lease["provider_name"]) if lease else None
    finally:
        if own_terminal_repo:
            _terminal_repo.close()
        if own_lease_repo:
            _lease_repo.close()


def resolve_existing_lease_cwd(
    lease_id: str,
    requested_cwd: str | None = None,
    db_path: Path | None = None,
    *,
    lease_repo: Any | None = None,
) -> str:
    if requested_cwd:
        return requested_cwd

    target_db = db_path or resolve_role_db_path(SQLiteDBRole.SANDBOX)
    _lease_repo = lease_repo
    own_lease_repo = _lease_repo is None
    if _lease_repo is None:
        _lease_repo = make_lease_repo(db_path=target_db)
    try:
        lease = _lease_repo.get(lease_id)
    finally:
        if own_lease_repo:
            _lease_repo.close()
    provider_name = str((lease or {}).get("provider_name") or "").strip()
    provider = _build_provider_from_name(provider_name) if provider_name else None
    if provider is not None:
        return resolve_provider_cwd(provider)
    raise ValueError("provider default cwd is required")


def bind_thread_to_existing_lease(
    thread_id: str,
    lease_id: str,
    *,
    cwd: str | None = None,
    db_path: Path | None = None,
    terminal_repo: Any | None = None,
    lease_repo: Any | None = None,
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
        initial_cwd = resolve_existing_lease_cwd(
            lease_id,
            cwd,
            db_path=target_db,
            lease_repo=lease_repo,
        )
        _terminal_repo.create(
            terminal_id=f"term-{uuid.uuid4().hex[:12]}",
            thread_id=thread_id,
            lease_id=lease_id,
            initial_cwd=initial_cwd,
        )
        return initial_cwd
    finally:
        if own_terminal_repo:
            _terminal_repo.close()


def resolve_existing_sandbox_lease(
    sandbox: Any,
    *,
    resolve_lease: Callable[[str], dict[str, Any] | None],
    db_path: Path | None = None,
    lease_repo: Any | None = None,
) -> dict[str, Any] | None:
    provider_name = str(
        (sandbox.get("provider_name") if isinstance(sandbox, dict) else getattr(sandbox, "provider_name", None)) or ""
    ).strip()
    provider_env_id = str(
        (sandbox.get("provider_env_id") if isinstance(sandbox, dict) else getattr(sandbox, "provider_env_id", None)) or ""
    ).strip()
    if provider_name and provider_env_id:
        # @@@existing-sandbox-live-lease-first
        # Existing-sandbox reuse should resolve the live lease from sandbox runtime identity first.
        # legacy_lease_id stays only as the compatibility fallback when the live provider-env binding
        # has not been materialized yet.
        target_db = db_path or resolve_role_db_path(SQLiteDBRole.SANDBOX)
        _lease_repo = lease_repo
        own_lease_repo = _lease_repo is None
        if _lease_repo is None:
            _lease_repo = make_lease_repo(db_path=target_db)
        try:
            lease = _lease_repo.find_by_instance(provider_name=provider_name, instance_id=provider_env_id)
            if lease is not None:
                return lease
        finally:
            if own_lease_repo:
                _lease_repo.close()
    config = sandbox.get("config") if isinstance(sandbox, dict) else getattr(sandbox, "config", None)
    if not isinstance(config, dict):
        raise RuntimeError("sandbox.config must be an object")
    legacy_lease_id = str(config.get("legacy_lease_id") or "").strip()
    if not legacy_lease_id:
        raise RuntimeError("sandbox.config.legacy_lease_id is required")
    return resolve_lease(legacy_lease_id)


def bind_thread_to_existing_sandbox(
    thread_id: str,
    sandbox: Any,
    *,
    resolve_lease: Callable[[str], dict[str, Any] | None],
    cwd: str | None = None,
    db_path: Path | None = None,
    terminal_repo: Any | None = None,
    lease_repo: Any | None = None,
) -> tuple[str, dict[str, Any]]:
    lease = resolve_existing_sandbox_lease(
        sandbox,
        resolve_lease=resolve_lease,
        db_path=db_path,
        lease_repo=lease_repo,
    )
    if lease is None:
        config = sandbox.get("config") if isinstance(sandbox, dict) else getattr(sandbox, "config", None)
        legacy_lease_id = str((config or {}).get("legacy_lease_id") or "").strip()
        raise RuntimeError(f"lease not found: {legacy_lease_id}")
    lease_id = str(lease.get("lease_id") or "").strip()
    if not lease_id:
        raise RuntimeError("lease.lease_id is required")
    initial_cwd = bind_thread_to_existing_lease(
        thread_id,
        lease_id,
        cwd=cwd,
        db_path=db_path,
        terminal_repo=terminal_repo,
        lease_repo=lease_repo,
    )
    return initial_cwd, lease


def bind_thread_to_existing_thread_lease(
    thread_id: str,
    source_thread_id: str,
    *,
    cwd: str | None = None,
    db_path: Path | None = None,
    terminal_repo: Any | None = None,
    lease_repo: Any | None = None,
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
    # @@@subagent-lease-reuse
    # Child threads need their own terminal/session state, but must attach
    # to the parent's existing lease instead of silently provisioning a new one.
    return bind_thread_to_existing_lease(
        thread_id,
        str(source_terminal["lease_id"]),
        cwd=cwd,
        db_path=target_db,
        terminal_repo=terminal_repo,
        lease_repo=lease_repo,
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
        self.lease_store = make_lease_repo(db_path=self.db_path)

        self.session_manager = ChatSessionManager(
            provider=provider,
            db_path=self.db_path,
            default_policy=ChatSessionPolicy(),
            chat_session_repo=make_chat_session_repo(db_path=self.db_path),
            terminal_repo=self.terminal_store,
            lease_repo=self.lease_store,
        )

        from sandbox.volume import SandboxVolume

        self.volume = SandboxVolume(
            provider=provider,
            provider_capability=self.provider_capability,
        )

    def _get_lease(self, lease_id: str):
        """Get lease as domain object, or None."""
        row = self.lease_store.get(lease_id)
        if row is None:
            return None
        return lease_from_row(row, self.db_path)

    def _create_lease(self, lease_id: str, provider_name: str):
        """Create lease and return as domain object."""
        row = self.lease_store.create(lease_id, provider_name)
        return lease_from_row(row, self.db_path)

    def get_terminal(self, thread_id: str):
        """Public API: get active terminal as domain object."""
        return self._get_active_terminal(thread_id)

    def get_lease(self, lease_id: str):
        """Public API: get lease as domain object."""
        return self._get_lease(lease_id)

    def _default_terminal_cwd(self) -> str:
        return resolve_provider_cwd(self.provider)

    def _requires_volume_bootstrap(self) -> bool:
        # @@@local-shell-no-volume-gate - local runtimes execute directly on the host
        # and should not fail to start a shell just because file-channel volume
        # metadata is absent or stored in a different backend.
        return self.provider_capability.runtime_kind != "local"

    def _destroy_daytona_managed_volume(self, lease_id: str) -> None:
        # @@@daytona-managed-volume-ref - daytona managed volumes now derive their backend
        # ref from lease identity directly, so cleanup no longer depends on lease volume metadata.
        self.provider.delete_managed_volume(f"leon-volume-{lease_id}")

    def _setup_mounts(self, thread_id: str) -> dict:
        """Mount the lease's volume into the sandbox. Pure sandbox-layer operation."""
        terminal = self._get_active_terminal(thread_id)
        if not terminal:
            raise ValueError(f"No active terminal for thread {thread_id}")
        lease = self._get_lease(terminal.lease_id)
        if not lease:
            raise ValueError(f"No volume for thread {thread_id}")
        remote_path = self.volume.resolve_mount_path()
        source_path = self._resolve_sync_source_path(thread_id)

        if self.provider_capability.runtime_kind != "daytona_pty":
            self.volume.mount(thread_id, source_path, remote_path)
            return {"source_path": source_path, "remote_path": remote_path}

        # @@@daytona-upgrade - first startup creates managed volume
        volume_name = self._upgrade_to_daytona_volume(
            thread_id,
            lease.lease_id,
            remote_path,
        )
        self.volume.mount_managed_volume(thread_id, volume_name, remote_path)

        return {"source_path": source_path, "remote_path": remote_path}

    def _upgrade_to_daytona_volume(self, thread_id: str, lease_id: str, remote_path: str):
        """Ensure Daytona managed volume exists and return provider backend ref."""

        try:
            volume_name = self.provider.create_managed_volume(lease_id, remote_path)
        except Exception as e:
            if "already exists" in str(e):
                volume_name = f"leon-volume-{lease_id}"
                logger.info("Daytona volume already exists: %s, reusing", volume_name)
                self.provider.wait_managed_volume_ready(volume_name)
            else:
                raise

        return volume_name

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

    def _get_thread_lease(self, thread_id: str):
        terminals = self._get_thread_terminals(thread_id)
        if not terminals:
            return None
        lease_ids = {terminal.lease_id for terminal in terminals}
        # @@@thread-single-lease-invariant - Terminals created via non-block must share one lease per thread.
        if len(lease_ids) != 1:
            raise RuntimeError(f"Thread {thread_id} has inconsistent lease_ids: {sorted(lease_ids)}")
        lease_id = next(iter(lease_ids))
        lease = self._get_lease(lease_id)
        if lease is None:
            return None
        self._assert_lease_provider(lease, thread_id)
        return lease

    def _thread_belongs_to_provider(self, thread_id: str) -> bool:
        terminals = self._get_thread_terminals(thread_id)
        if not terminals:
            return False
        lease = self._get_lease(terminals[0].lease_id)
        return bool(lease and lease.provider_name == self.provider.name)

    def _resolve_sync_source_path(self, thread_id: str) -> Path:
        # @@@sync-source-truth - sync no longer needs volume metadata truth; it only needs
        # the workspace-owned local staging root that backs the current file channel.
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

    def _skip_volume_sync_for_local_lease(self, lease) -> bool:
        # @@@local-no-volume-sync - local sessions execute directly in host cwd, so upload/download
        # must always no-op there rather than reactivating volume-backed sync.
        return lease is not None and not self._requires_volume_bootstrap()

    def _sync_to_sandbox(self, thread_id: str, instance_id: str, source=None, files: list[str] | None = None) -> None:
        if source is None:
            lease = self._get_thread_lease(thread_id)
            if self._skip_volume_sync_for_local_lease(lease):
                return
            source = self._resolve_sync_source_path(thread_id)
        self.volume.sync_upload(thread_id, instance_id, source, self.volume.resolve_mount_path(), files=files)

    def _sync_from_sandbox(self, thread_id: str, instance_id: str, source=None) -> None:
        if source is None:
            lease = self._get_thread_lease(thread_id)
            if self._skip_volume_sync_for_local_lease(lease):
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
        instance = session.lease.get_instance()
        if not instance:
            return False
        self._sync_to_sandbox(thread_id, instance.instance_id, files=files)
        return True

    def close(self):
        self.session_manager.close(reason="manager_close")
        self.terminal_store.close()
        self.lease_store.close()

    def get_sandbox(self, thread_id: str, bind_mounts: list | None = None) -> SandboxCapability:
        from sandbox.thread_context import set_current_thread_id

        set_current_thread_id(thread_id)

        terminal = self._get_active_terminal(thread_id)
        session = self.session_manager.get(thread_id, terminal.terminal_id) if terminal else None
        if session:
            self._assert_lease_provider(session.lease, thread_id)
            # @@@activity-resume - Any new activity against a paused thread must resume before command execution.
            if session.status == "paused" or getattr(session.lease, "observed_state", None) == "paused":
                if not self.resume_session(thread_id, source="auto_resume"):
                    raise RuntimeError(f"Failed to resume paused session for thread {thread_id}")
                session = self.session_manager.get(thread_id, session.terminal.terminal_id)
                if not session:
                    raise RuntimeError(f"Session disappeared after resume for thread {thread_id}")
                self._assert_lease_provider(session.lease, thread_id)
            # Stamp bind_mounts on provider thread state so lazy create_session paths pick them up
            if bind_mounts:
                self.provider.set_thread_bind_mounts(thread_id, bind_mounts)
            self._ensure_bound_instance(session.lease)
            return SandboxCapability(session, manager=self)

        if not terminal:
            terminal_id = f"term-{uuid.uuid4().hex[:12]}"
            lease_id = f"lease-{uuid.uuid4().hex[:12]}"
            lease = self._create_lease(lease_id, self.provider.name)
            initial_cwd = self._default_terminal_cwd()
            terminal = terminal_from_row(
                self.terminal_store.create(
                    terminal_id=terminal_id,
                    thread_id=thread_id,
                    lease_id=lease_id,
                    initial_cwd=initial_cwd,
                ),
                self.db_path,
            )
        else:
            lease = self._get_lease(terminal.lease_id)
            if not lease:
                lease = self._create_lease(terminal.lease_id, self.provider.name)
            self._assert_lease_provider(lease, thread_id)
            if lease.observed_state == "paused":
                # @@@paused-lease-rehydrate - a persisted thread can lose its in-memory chat session
                # while the lease stays paused in storage; resume before reconstructing capability.
                if not self.resume_session(thread_id, source="auto_resume"):
                    raise RuntimeError(f"Failed to resume paused session for thread {thread_id}")
                session = self.session_manager.get(thread_id, terminal.terminal_id)
                if session:
                    self._assert_lease_provider(session.lease, thread_id)
                    self._ensure_bound_instance(session.lease)
                    return SandboxCapability(session, manager=self)
                lease = self._get_lease(terminal.lease_id)
                if not lease:
                    raise RuntimeError(f"Lease disappeared after resume for thread {thread_id}")
                self._assert_lease_provider(lease, thread_id)

        # Stamp bind_mounts on provider thread state so lazy create_session paths pick them up
        if bind_mounts:
            self.provider.set_thread_bind_mounts(thread_id, bind_mounts)

        storage = None
        if self._requires_volume_bootstrap():
            # @@@volume-strategy-gate - remote runtimes need volume mount/sync before first command.
            storage = self._setup_mounts(thread_id)

        self._ensure_bound_instance(lease)

        # @@@force-instance-for-sync - Non-eager providers (E2B, Daytona, etc.) create instances lazily.
        # Force instance creation here so workspace sync can upload files before tools run.
        if not lease.get_instance():
            lease.ensure_active_instance(self.provider)

        instance = lease.get_instance()
        if instance:
            recipe_env = bootstrap_recipe(self.provider, session_id=instance.instance_id, recipe=lease.recipe)
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
            lease=lease,
        )

        if instance and storage is not None:
            # @@@workspace-upload - sync files to sandbox after creation
            self._sync_to_sandbox(thread_id, instance.instance_id, source=storage["source_path"])
            self._fire_session_ready(instance.instance_id, "create")

        return SandboxCapability(session, manager=self)

    def create_background_command_session(self, thread_id: str, initial_cwd: str) -> Any:
        default_row = self.terminal_store.get_default(thread_id)
        if default_row is None:
            # Fallback: pointer row may predate default_terminal_id tracking; try active terminal
            default_row = self.terminal_store.get_active(thread_id)
        if default_row is None:
            raise RuntimeError(f"Thread {thread_id} has no default terminal")
        default_terminal = terminal_from_row(default_row, self.db_path)
        lease = self._get_lease(default_terminal.lease_id)
        if lease is None:
            raise RuntimeError(f"Missing lease {default_terminal.lease_id} for thread {thread_id}")
        self._assert_lease_provider(lease, thread_id)

        inherited = default_terminal.get_state()
        terminal_id = f"term-{uuid.uuid4().hex[:12]}"
        terminal = terminal_from_row(
            self.terminal_store.create(
                terminal_id=terminal_id,
                thread_id=thread_id,
                lease_id=lease.lease_id,
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
            lease=lease,
        )

    def _terminal_is_busy(self, terminal_id: str) -> bool:
        """Return True if this terminal has a running command."""
        if not terminal_id:
            return False
        if not self.db_path.exists():
            return False
        return self.session_manager._repo.terminal_has_running_command(terminal_id)

    def _lease_is_busy(self, lease_id: str) -> bool:
        """Return True if any terminal under this lease has a running command."""
        if not lease_id:
            return False
        if not self.db_path.exists():
            return False
        return self.session_manager._repo.lease_has_running_command(lease_id)

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
            lease = self._get_lease(terminal.lease_id) if terminal else None
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
                    capability = self.provider.get_capability()
                    # @@@idle-reaper-reclaim-contract - idle timeout must reclaim remote resources; providers
                    # that cannot pause should destroy instead of repeatedly throwing unsupported-operation noise.
                    if status == "running" and self.provider.name != "local":
                        try:
                            if capability.can_pause:
                                reclaimed = lease.pause_instance(self.provider, source="idle_reaper")
                            elif capability.can_destroy:
                                reclaimed = lease.destroy_instance(self.provider, source="idle_reaper") is None
                            else:
                                print(
                                    f"[idle-reaper] provider {self.provider.name} cannot reclaim expired lease "
                                    f"{lease.lease_id} for thread {thread_id}"
                                )
                                continue
                        except Exception as exc:
                            print(f"[idle-reaper] failed to reclaim expired lease {lease.lease_id} for thread {thread_id}: {exc}")
                            continue
                        if not reclaimed:
                            print(f"[idle-reaper] failed to reclaim expired lease {lease.lease_id} for thread {thread_id}")
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
                    self._sync_from_sandbox(thread_id, instance.instance_id)
                except Exception:
                    logger.error("Failed to download workspace before pause — agent changes may be lost", exc_info=True)
                    raise
            if not lease.pause_instance(self.provider, source="user_pause"):
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

        lease = self._get_thread_lease(thread_id)
        if not lease:
            return False

        if not lease.resume_instance(self.provider, source=source):
            return False

        # @@@workspace-upload-on-resume - re-sync files that may have been uploaded while paused
        instance = lease.get_instance()
        if instance:
            self._sync_to_sandbox(thread_id, instance.instance_id)

        resumed_any = False
        for terminal in terminals:
            session = self.session_manager.get(thread_id, terminal.terminal_id)
            if session:
                session.lease = lease
                runtime = getattr(session, "runtime", None)
                if runtime is not None:
                    runtime.lease = lease
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
        """Destroy physical resources and detach thread from terminal/lease records."""
        terminal_rows = self.terminal_store.list_by_thread(thread_id)
        terminals = [terminal_from_row(r, self.db_path) for r in terminal_rows]
        if not terminals:
            return False

        # @@@workspace-download-before-destroy - sync files before destroy
        lease = self._get_thread_lease(thread_id)
        if lease and lease.observed_state == "running":
            instance = lease.get_instance()
            if instance:
                try:
                    self._sync_from_sandbox(thread_id, instance.instance_id)
                except Exception:
                    logger.error("Failed to download workspace before destroy — agent changes are lost", exc_info=True)
                    raise
        self.volume.clear_sync_state(thread_id)

        lease_ids = {terminal.lease_id for terminal in terminals}

        self.session_manager.delete_thread(thread_id, reason="thread_deleted")

        for terminal in terminals:
            self.terminal_store.delete(terminal.terminal_id)

        for lease_id in lease_ids:
            # @@@shared-lease-destroy-boundary - destroying one thread must not tear down
            # a lease that still has surviving terminals bound to it.
            lease_in_use = any(row.get("lease_id") == lease_id for row in self.terminal_store.list_all())
            if lease_in_use:
                continue
            if not self.destroy_lease_resources(lease_id):
                raise RuntimeError(f"Missing lease {lease_id} for thread {thread_id}")
        return True

    def destroy_lease_resources(self, lease_id: str) -> bool:
        lease = self._get_lease(lease_id)
        if not lease:
            return False
        if any(row.get("lease_id") == lease_id for row in self.terminal_store.list_all()):
            raise RuntimeError(f"Lease {lease_id} still has bound terminals")
        lease.destroy_instance(self.provider)
        if self.provider_capability.runtime_kind == "daytona_pty":
            self._destroy_daytona_managed_volume(lease_id)
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
            lease = self._get_lease(lease_id)
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

        list_provider_sessions = getattr(self.provider, "list_provider_sessions", None)
        provider_sessions = []
        if callable(list_provider_sessions):
            try:
                raw_provider_sessions = list_provider_sessions()
                provider_sessions = raw_provider_sessions if isinstance(raw_provider_sessions, list) else []
            except Exception:
                logger.warning("Failed to list provider sessions for %s", self.provider.name, exc_info=True)
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
