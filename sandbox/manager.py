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
from sandbox.lease import lease_from_row
from sandbox.provider import SandboxProvider
from sandbox.recipes import bootstrap_recipe
from sandbox.terminal import TerminalState, terminal_from_row
from storage.providers.sqlite.chat_session_repo import SQLiteChatSessionRepo
from storage.providers.sqlite.kernel import SQLiteDBRole, resolve_role_db_path
from storage.providers.sqlite.lease_repo import SQLiteLeaseRepo
from storage.providers.sqlite.terminal_repo import SQLiteTerminalRepo
from storage.runtime import build_storage_container, build_thread_repo

logger = logging.getLogger(__name__)


def resolve_provider_cwd(provider) -> str:
    """Get the default working directory for a provider."""
    for attr in ("default_cwd", "default_context_path", "mount_path"):
        val = getattr(provider, attr, None)
        if isinstance(val, str) and val:
            return val
    return "/home/user"


def lookup_sandbox_for_thread(thread_id: str, db_path: Path | None = None) -> str | None:
    target_db = db_path or resolve_role_db_path(SQLiteDBRole.SANDBOX)
    if not target_db.exists():
        return None

    terminal_repo = SQLiteTerminalRepo(db_path=target_db)
    lease_repo = SQLiteLeaseRepo(db_path=target_db)
    try:
        terminals = terminal_repo.list_by_thread(thread_id)
        if not terminals:
            return None
        lease_id = str(terminals[0]["lease_id"])
        lease = lease_repo.get(lease_id)
        return str(lease["provider_name"]) if lease else None
    finally:
        terminal_repo.close()
        lease_repo.close()


def resolve_existing_lease_cwd(
    lease_id: str,
    fallback_cwd: str | None = None,
    db_path: Path | None = None,
) -> str:
    if fallback_cwd:
        return fallback_cwd

    target_db = db_path or resolve_role_db_path(SQLiteDBRole.SANDBOX)
    terminal_repo = SQLiteTerminalRepo(db_path=target_db)
    try:
        row = terminal_repo.get_latest_by_lease(lease_id)
    finally:
        terminal_repo.close()
    if row and row.get("cwd"):
        return str(row["cwd"])
    return str(Path.home())


def bind_thread_to_existing_lease(
    thread_id: str,
    lease_id: str,
    *,
    cwd: str | None = None,
    db_path: Path | None = None,
) -> str:
    target_db = db_path or resolve_role_db_path(SQLiteDBRole.SANDBOX)
    terminal_repo = SQLiteTerminalRepo(db_path=target_db)
    try:
        existing = terminal_repo.get_active(thread_id)
        if existing is not None:
            return str(existing["cwd"])
        initial_cwd = resolve_existing_lease_cwd(lease_id, cwd, db_path=target_db)
        terminal_repo.create(
            terminal_id=f"term-{uuid.uuid4().hex[:12]}",
            thread_id=thread_id,
            lease_id=lease_id,
            initial_cwd=initial_cwd,
        )
        return initial_cwd
    finally:
        terminal_repo.close()


def bind_thread_to_existing_thread_lease(
    thread_id: str,
    source_thread_id: str,
    *,
    cwd: str | None = None,
    db_path: Path | None = None,
) -> str | None:
    target_db = db_path or resolve_role_db_path(SQLiteDBRole.SANDBOX)
    terminal_repo = SQLiteTerminalRepo(db_path=target_db)
    try:
        source_terminal = terminal_repo.get_active(source_thread_id)
    finally:
        terminal_repo.close()
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
        self.terminal_store = SQLiteTerminalRepo(db_path=self.db_path)
        self.lease_store = SQLiteLeaseRepo(db_path=self.db_path)

        self.session_manager = ChatSessionManager(
            provider=provider,
            db_path=self.db_path,
            default_policy=ChatSessionPolicy(),
            chat_session_repo=SQLiteChatSessionRepo(db_path=self.db_path),
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
        return lease_from_row(row, self.lease_store.db_path)

    def _create_lease(self, lease_id: str, provider_name: str, volume_id: str | None = None):
        """Create lease and return as domain object."""
        row = self.lease_store.create(lease_id, provider_name, volume_id=volume_id)
        return lease_from_row(row, self.lease_store.db_path)

    def get_terminal(self, thread_id: str):
        """Public API: get active terminal as domain object."""
        return self._get_active_terminal(thread_id)

    def get_lease(self, lease_id: str):
        """Public API: get lease as domain object."""
        return self._get_lease(lease_id)

    def _default_terminal_cwd(self) -> str:
        return resolve_provider_cwd(self.provider)

    def _sandbox_volume_repo(self):
        # @@@volume-repo-align - thread creation persists volume metadata through the
        # active storage container; sandbox startup must read the same repo instead
        # of hardcoding SQLite or Supabase-backed threads lose their volume row.
        container = build_storage_container(main_db_path=resolve_role_db_path(SQLiteDBRole.MAIN))
        return container.sandbox_volume_repo()

    def _requires_volume_bootstrap(self) -> bool:
        # @@@local-shell-no-volume-gate - local runtimes execute directly on the host
        # and should not fail to start a shell just because file-channel volume
        # metadata is absent or stored in a different backend.
        return self.provider_capability.runtime_kind != "local"

    def _ensure_thread_volume(self, thread_id: str, lease) -> None:
        if not self._requires_volume_bootstrap() or lease.volume_id:
            return

        volume_id = str(uuid.uuid4())
        self._create_volume_entry(thread_id, volume_id)

        # @@@remote-volume-self-heal - legacy threads can lose their eager-created lease row
        # and get rebound through manager recovery; persist a replacement volume_id before mount/sync.
        self.lease_store.set_volume_id(lease.lease_id, volume_id)
        lease.volume_id = volume_id

    def _create_volume_entry(self, thread_id: str, volume_id: str) -> None:
        import json
        import os

        from sandbox.volume_source import HostVolume

        now_str = datetime.now().isoformat()
        volume_root = Path(os.environ.get("LEON_SANDBOX_VOLUME_ROOT", str(user_home_path("volumes")))).expanduser().resolve()
        volume_root.mkdir(parents=True, exist_ok=True)
        source = HostVolume(volume_root / volume_id)

        repo = self._sandbox_volume_repo()
        try:
            repo.create(volume_id, json.dumps(source.serialize()), f"vol-{thread_id}", now_str)
        finally:
            repo.close()

    def _resolve_volume_entry(self, thread_id: str, lease) -> dict[str, Any]:
        repo = self._sandbox_volume_repo()
        try:
            entry = repo.get(lease.volume_id)
        finally:
            repo.close()
        if entry:
            return entry
        # @@@missing-volume-row-self-heal - old remote threads can retain a live lease.volume_id
        # after the sandbox volume row was pruned; recreate the row in place before mount/sync.
        self._create_volume_entry(thread_id, lease.volume_id)
        repo = self._sandbox_volume_repo()
        try:
            entry = repo.get(lease.volume_id)
        finally:
            repo.close()
        if not entry:
            raise ValueError(f"Volume not found: {lease.volume_id}")
        return entry

    def _setup_mounts(self, thread_id: str) -> dict:
        """Mount the lease's volume into the sandbox. Pure sandbox-layer operation."""
        import json

        from sandbox.volume_source import DaytonaVolume, deserialize_volume_source

        terminal = self._get_active_terminal(thread_id)
        if not terminal:
            raise ValueError(f"No active terminal for thread {thread_id}")
        lease = self._get_lease(terminal.lease_id)
        if not lease:
            raise ValueError(f"No volume for thread {thread_id}")
        self._ensure_thread_volume(thread_id, lease)
        entry = self._resolve_volume_entry(thread_id, lease)

        source = deserialize_volume_source(json.loads(entry["source"]))
        volume_id = lease.volume_id
        remote_path = self.volume.resolve_mount_path()

        # @@@daytona-upgrade - first startup creates managed volume
        if self.provider_capability.runtime_kind == "daytona_pty" and not isinstance(source, DaytonaVolume):
            source = self._upgrade_to_daytona_volume(
                thread_id,
                source,
                volume_id,
                remote_path,
            )

        if isinstance(source, DaytonaVolume):
            self.volume.mount_managed_volume(thread_id, source.volume_name, remote_path)
        else:
            self.volume.mount(thread_id, source, remote_path)

        return {"source": source, "remote_path": remote_path}

    def _upgrade_to_daytona_volume(self, thread_id: str, current_source, volume_id: str, remote_path: str):
        """First Daytona sandbox start: create managed volume, upgrade VolumeSource in DB."""
        import json

        from sandbox.volume_source import DaytonaVolume

        # @@@member-id-for-volume-naming - read from thread config in leon.db
        member_id = "unknown"
        thread_repo = build_thread_repo(main_db_path=resolve_role_db_path(SQLiteDBRole.MAIN))
        try:
            row = thread_repo.get_by_id(thread_id)
            if row:
                member_id = str(row["member_id"])
        except Exception:
            pass
        finally:
            thread_repo.close()

        try:
            volume_name = self.provider.create_managed_volume(member_id, remote_path)
        except Exception as e:
            if "already exists" in str(e):
                volume_name = f"leon-volume-{member_id}"
                logger.info("Daytona volume already exists: %s, reusing", volume_name)
                self.provider.wait_managed_volume_ready(volume_name)
            else:
                raise

        new_source = DaytonaVolume(
            staging_path=current_source.host_path,
            volume_name=volume_name,
        )

        repo = self._sandbox_volume_repo()
        try:
            repo.update_source(volume_id, json.dumps(new_source.serialize()))
        finally:
            repo.close()

        return new_source

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
            return terminal_from_row(row, self.terminal_store.db_path)
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
        rows = self.terminal_store.list_by_thread(thread_id)
        return [terminal_from_row(row, self.terminal_store.db_path) for row in rows]

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

    def resolve_volume_source(self, thread_id: str):
        """Resolve VolumeSource for a thread via lease chain. Pure sandbox-layer lookup."""
        import json

        from sandbox.volume_source import deserialize_volume_source

        terminal = self._get_active_terminal(thread_id)
        if not terminal:
            raise ValueError(f"No active terminal for thread {thread_id}")
        lease = self._get_lease(terminal.lease_id)
        if not lease:
            raise ValueError(f"No volume for thread {thread_id}")
        self._ensure_thread_volume(thread_id, lease)
        entry = self._resolve_volume_entry(thread_id, lease)
        return deserialize_volume_source(json.loads(entry["source"]))

    def _sync_to_sandbox(self, thread_id: str, instance_id: str, source=None, files: list[str] | None = None) -> None:
        if source is None:
            source = self.resolve_volume_source(thread_id)
        self.volume.sync_upload(thread_id, instance_id, source, self.volume.resolve_mount_path(), files=files)

    def _sync_from_sandbox(self, thread_id: str, instance_id: str, source=None) -> None:
        if source is None:
            source = self.resolve_volume_source(thread_id)
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
            if session.status == "paused":
                if not self.resume_session(thread_id, source="auto_resume"):
                    raise RuntimeError(f"Failed to resume paused session for thread {thread_id}")
                session = self.session_manager.get(thread_id, session.terminal.terminal_id)
                if not session:
                    raise RuntimeError(f"Session disappeared after resume for thread {thread_id}")
                self._assert_lease_provider(session.lease, thread_id)
            # Stamp bind_mounts on lease so lazy creation paths pick them up
            if bind_mounts:
                session.lease.bind_mounts = bind_mounts
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
                self.terminal_store.db_path,
            )
        else:
            lease = self._get_lease(terminal.lease_id)
            if not lease:
                lease = self._create_lease(terminal.lease_id, self.provider.name)
            self._assert_lease_provider(lease, thread_id)

        # Stamp bind_mounts on lease so lazy creation paths pick them up
        if bind_mounts:
            lease.bind_mounts = bind_mounts

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
            self._sync_to_sandbox(thread_id, instance.instance_id, source=storage["source"])
            self._fire_session_ready(instance.instance_id, "create")

        return SandboxCapability(session, manager=self)

    def create_background_command_session(self, thread_id: str, initial_cwd: str) -> Any:
        default_row = self.terminal_store.get_default(thread_id)
        if default_row is None:
            # Fallback: pointer row may predate default_terminal_id tracking; try active terminal
            default_row = self.terminal_store.get_active(thread_id)
        if default_row is None:
            raise RuntimeError(f"Thread {thread_id} has no default terminal")
        default_terminal = terminal_from_row(default_row, self.terminal_store.db_path)
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
            self.terminal_store.db_path,
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
            terminal_row = self.terminal_store.get_by_id(str(terminal_id)) if terminal_id else None
            terminal = terminal_from_row(terminal_row, self.terminal_store.db_path) if terminal_row else None
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
        terminals = [terminal_from_row(r, self.terminal_store.db_path) for r in terminal_rows]
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

        for terminal in terminals:
            session = self.session_manager.get(thread_id, terminal.terminal_id)
            if session:
                self.session_manager.delete(session.session_id, reason="thread_deleted")

        for terminal in terminals:
            self.terminal_store.delete(terminal.terminal_id)

        for lease_id in lease_ids:
            lease = self._get_lease(lease_id)
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

        if hasattr(self.provider, "list_provider_sessions"):
            try:
                provider_sessions = self.provider.list_provider_sessions() or []
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
