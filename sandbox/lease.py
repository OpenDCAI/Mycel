"""SandboxLease - durable compute handle with lease-level state machine.

Architecture:
    SandboxLease (durable) -> SandboxInstance (ephemeral)

State machine contract:
- Physical lifecycle writes must go through SQLiteLease.apply(event).
- Lease snapshot stores desired_state + observed_state + version.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from storage.providers.sqlite.kernel import connect_sqlite

from sandbox.config import DEFAULT_DB_PATH
from sandbox.lifecycle import (
    LeaseInstanceState,
    assert_lease_instance_transition,
    parse_lease_instance_state,
)

if TYPE_CHECKING:
    from sandbox.provider import SandboxProvider
    from storage.providers.sqlite.sandbox_repository_protocol import SandboxRepositoryProtocol

LEASE_FRESHNESS_TTL_SEC = 3.0

REQUIRED_LEASE_COLUMNS = {
    "lease_id",
    "provider_name",
    "workspace_key",
    "current_instance_id",
    "instance_created_at",
    "desired_state",
    "observed_state",
    "version",
    "observed_at",
    "last_error",
    "needs_refresh",
    "refresh_hint_at",
    "status",
    "volume_id",
    "created_at",
    "updated_at",
}
REQUIRED_INSTANCE_COLUMNS = {
    "instance_id",
    "lease_id",
    "provider_session_id",
    "status",
    "created_at",
    "last_seen_at",
}
REQUIRED_EVENT_COLUMNS = {
    "event_id",
    "lease_id",
    "event_type",
    "source",
    "payload_json",
    "error",
    "created_at",
}


def _connect(db_path: Path) -> sqlite3.Connection:
    return connect_sqlite(db_path)


@dataclass
class SandboxInstance:
    """Ephemeral sandbox compute instance."""

    instance_id: str
    provider_name: str
    status: str
    created_at: datetime


class SandboxLease(ABC):
    """Durable shared compute handle."""

    def __init__(
        self,
        lease_id: str,
        provider_name: str,
        current_instance: SandboxInstance | None = None,
        status: str = "active",
        workspace_key: str | None = None,
        desired_state: str = "running",
        observed_state: str = "detached",
        version: int = 0,
        observed_at: datetime | None = None,
        last_error: str | None = None,
        needs_refresh: bool = False,
        refresh_hint_at: datetime | None = None,
        volume_id: str | None = None,
    ):
        self.lease_id = lease_id
        self.provider_name = provider_name
        self._current_instance = current_instance
        self.status = status
        self.workspace_key = workspace_key
        self.desired_state = desired_state
        self.observed_state = observed_state
        self.version = version
        self.observed_at = observed_at
        self.last_error = last_error
        self.needs_refresh = needs_refresh
        self.refresh_hint_at = refresh_hint_at
        self.volume_id = volume_id

    # @@@compat-refresh-error - legacy callers still read refresh_error while storage canonicalized to last_error.
    @property
    def refresh_error(self) -> str | None:
        return self.last_error

    @refresh_error.setter
    def refresh_error(self, value: str | None) -> None:
        self.last_error = value

    def get_instance(self) -> SandboxInstance | None:
        return self._current_instance

    @abstractmethod
    def ensure_active_instance(self, provider: SandboxProvider) -> SandboxInstance: ...

    @abstractmethod
    def destroy_instance(self, provider: SandboxProvider, *, source: str = "api") -> None: ...

    @abstractmethod
    def pause_instance(self, provider: SandboxProvider, *, source: str = "api") -> bool: ...

    @abstractmethod
    def resume_instance(self, provider: SandboxProvider, *, source: str = "api") -> bool: ...

    @abstractmethod
    def refresh_instance_status(
        self,
        provider: SandboxProvider,
        *,
        force: bool = False,
        max_age_sec: float = LEASE_FRESHNESS_TTL_SEC,
    ) -> str: ...

    @abstractmethod
    def mark_needs_refresh(self, hint_at: datetime | None = None) -> None: ...

    @abstractmethod
    def apply(
        self,
        provider: SandboxProvider,
        *,
        event_type: str,
        source: str,
        payload: dict[str, Any] | None = None,
        event_id: str | None = None,
    ) -> dict[str, Any]: ...


class SQLiteLease(SandboxLease):
    """SQLite-backed lease implementation."""

    _lock_guard = threading.Lock()
    _lease_locks: dict[str, threading.RLock] = {}

    def __init__(
        self,
        lease_id: str,
        provider_name: str,
        current_instance: SandboxInstance | None = None,
        db_path: Path = DEFAULT_DB_PATH,
        status: str = "active",
        workspace_key: str | None = None,
        desired_state: str = "running",
        observed_state: str = "detached",
        version: int = 0,
        observed_at: datetime | None = None,
        last_error: str | None = None,
        needs_refresh: bool = False,
        refresh_hint_at: datetime | None = None,
        volume_id: str | None = None,
    ):
        super().__init__(
            lease_id=lease_id,
            provider_name=provider_name,
            current_instance=current_instance,
            status=status,
            workspace_key=workspace_key,
            desired_state=desired_state,
            observed_state=observed_state,
            version=version,
            observed_at=observed_at,
            last_error=last_error,
            needs_refresh=needs_refresh,
            refresh_hint_at=refresh_hint_at,
            volume_id=volume_id,
        )
        self.db_path = db_path
        self._detached_instance: SandboxInstance | None = None

    def _instance_lock(self) -> threading.RLock:
        with self._lock_guard:
            lock = self._lease_locks.get(self.lease_id)
            if lock is None:
                # @@@reentrant-lease-lock - apply() may be called inside ensure_active_instance critical sections.
                lock = threading.RLock()
                self._lease_locks[self.lease_id] = lock
            return lock

    def _is_fresh(self, max_age_sec: float = LEASE_FRESHNESS_TTL_SEC) -> bool:
        if not self.observed_at:
            return False
        return (datetime.now() - self.observed_at).total_seconds() <= max_age_sec

    def _instance_state(self) -> LeaseInstanceState:
        if not self._current_instance:
            return LeaseInstanceState.DETACHED
        return parse_lease_instance_state(self._current_instance.status)

    def _normalize_provider_state(self, raw: str) -> str:
        lowered = raw.lower().strip()
        if lowered in {"running", "paused", "unknown"}:
            return lowered
        if lowered in {"deleted", "dead", "stopped", "detached"}:
            return "detached"
        return "unknown"

    def _set_observed_state(self, observed: str, *, reason: str) -> None:
        if observed in {"running", "paused", "unknown"} and not self._current_instance:
            if observed == "unknown":
                self.observed_state = observed
                return
            raise RuntimeError(
                f"Lease {self.lease_id}: cannot set observed={observed} without bound instance ({reason})"
            )

        if observed == "running":
            assert_lease_instance_transition(self._instance_state(), LeaseInstanceState.RUNNING, reason=reason)
            if self._current_instance:
                self._current_instance.status = "running"
            self.observed_state = "running"
            return

        if observed == "paused":
            assert_lease_instance_transition(self._instance_state(), LeaseInstanceState.PAUSED, reason=reason)
            if self._current_instance:
                self._current_instance.status = "paused"
            self.observed_state = "paused"
            return

        if observed == "detached":
            assert_lease_instance_transition(self._instance_state(), LeaseInstanceState.DETACHED, reason=reason)
            self._detached_instance = self._current_instance
            self._current_instance = None
            self.observed_state = "detached"
            return

        if observed == "unknown":
            if self._current_instance:
                assert_lease_instance_transition(self._instance_state(), LeaseInstanceState.UNKNOWN, reason=reason)
                self._current_instance.status = "unknown"
            self.observed_state = "unknown"
            return

        raise RuntimeError(f"Lease {self.lease_id}: invalid observed state '{observed}'")

    def _snapshot(self) -> dict[str, Any]:
        return {
            "lease_id": self.lease_id,
            "provider_name": self.provider_name,
            "status": self.status,
            "desired_state": self.desired_state,
            "observed_state": self.observed_state,
            "version": self.version,
            "observed_at": self.observed_at.isoformat() if self.observed_at else None,
            "last_error": self.last_error,
            "needs_refresh": self.needs_refresh,
            "refresh_hint_at": self.refresh_hint_at.isoformat() if self.refresh_hint_at else None,
            "instance": {
                "instance_id": self._current_instance.instance_id if self._current_instance else None,
                "state": self._current_instance.status if self._current_instance else None,
                "started_at": self._current_instance.created_at.isoformat() if self._current_instance else None,
            },
        }

    def _append_event(
        self,
        *,
        event_type: str,
        source: str,
        payload: dict[str, Any],
        error: str | None,
        event_id: str,
        conn: sqlite3.Connection | None = None,
    ) -> None:
        should_commit = conn is None
        target = conn or _connect(self.db_path)
        try:
            target.execute(
                """
                INSERT INTO lease_events (event_id, lease_id, event_type, source, payload_json, error, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    self.lease_id,
                    event_type,
                    source,
                    json.dumps(payload),
                    error,
                    datetime.now().isoformat(),
                ),
            )
            if should_commit:
                target.commit()
        finally:
            if should_commit:
                target.close()

    def _persist_snapshot(self, conn: sqlite3.Connection | None = None) -> bool:
        should_commit = conn is None
        target = conn or _connect(self.db_path)
        detached_instance = self._detached_instance
        try:
            target.execute(
                """
                UPDATE sandbox_leases
                SET current_instance_id = ?,
                    instance_created_at = ?,
                    desired_state = ?,
                    observed_state = ?,
                    instance_status = ?,
                    version = ?,
                    observed_at = ?,
                    last_error = ?,
                    needs_refresh = ?,
                    refresh_hint_at = ?,
                    status = ?,
                    updated_at = ?
                WHERE lease_id = ?
                """,
                (
                    self._current_instance.instance_id if self._current_instance else None,
                    self._current_instance.created_at.isoformat() if self._current_instance else None,
                    self.desired_state,
                    self.observed_state,
                    self.observed_state,
                    self.version,
                    self.observed_at.isoformat() if self.observed_at else None,
                    self.last_error,
                    1 if self.needs_refresh else 0,
                    self.refresh_hint_at.isoformat() if self.refresh_hint_at else None,
                    self.status,
                    datetime.now().isoformat(),
                    self.lease_id,
                ),
            )

            if self._current_instance:
                target.execute(
                    """
                    INSERT INTO sandbox_instances (instance_id, lease_id, provider_session_id, status, created_at, last_seen_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(instance_id) DO UPDATE SET
                        lease_id = excluded.lease_id,
                        status = excluded.status,
                        last_seen_at = excluded.last_seen_at
                    """,
                    (
                        self._current_instance.instance_id,
                        self.lease_id,
                        self._current_instance.instance_id,
                        self._current_instance.status,
                        self._current_instance.created_at.isoformat(),
                        datetime.now().isoformat(),
                    ),
                )

            if detached_instance:
                target.execute(
                    """
                    UPDATE sandbox_instances
                    SET status = ?, last_seen_at = ?
                    WHERE instance_id = ?
                    """,
                    (
                        "stopped",
                        datetime.now().isoformat(),
                        detached_instance.instance_id,
                    ),
                )
            if should_commit:
                target.commit()
                if detached_instance:
                    self._detached_instance = None
            return detached_instance is not None
        finally:
            if should_commit:
                target.close()

    def _persist_lease_metadata(self, conn: sqlite3.Connection | None = None) -> None:
        should_commit = conn is None
        target = conn or _connect(self.db_path)
        try:
            target.execute(
                """
                UPDATE sandbox_leases
                SET desired_state = ?,
                    observed_state = ?,
                    instance_status = ?,
                    version = ?,
                    observed_at = ?,
                    last_error = ?,
                    needs_refresh = ?,
                    refresh_hint_at = ?,
                    status = ?,
                    updated_at = ?
                WHERE lease_id = ?
                """,
                (
                    self.desired_state,
                    self.observed_state,
                    self.observed_state,
                    self.version,
                    self.observed_at.isoformat() if self.observed_at else None,
                    self.last_error,
                    1 if self.needs_refresh else 0,
                    self.refresh_hint_at.isoformat() if self.refresh_hint_at else None,
                    self.status,
                    datetime.now().isoformat(),
                    self.lease_id,
                ),
            )
            if should_commit:
                target.commit()
        finally:
            if should_commit:
                target.close()

    def _record_provider_error(self, message: str) -> None:
        self.last_error = message[:500]
        self.needs_refresh = True
        self.refresh_hint_at = datetime.now()
        self.version += 1
        self._persist_lease_metadata()

    def _sync_from(self, other: SQLiteLease) -> None:
        self._current_instance = other._current_instance
        self.status = other.status
        self.workspace_key = other.workspace_key
        self.desired_state = other.desired_state
        self.observed_state = other.observed_state
        self.version = other.version
        self.observed_at = other.observed_at
        self.last_error = other.last_error
        self.needs_refresh = other.needs_refresh
        self.volume_id = other.volume_id
        self.refresh_hint_at = other.refresh_hint_at

    def apply(
        self,
        provider: SandboxProvider,
        *,
        event_type: str,
        source: str,
        payload: dict[str, Any] | None = None,
        event_id: str | None = None,
    ) -> dict[str, Any]:
        payload = payload or {}
        eid = event_id or f"evt-{uuid.uuid4().hex}"

        with self._instance_lock():
            if event_type != "intent.ensure_running":
                latest = LeaseStore(db_path=self.db_path).get(self.lease_id)
                if isinstance(latest, SQLiteLease):
                    self._sync_from(latest)
            now = datetime.now()

            try:
                if event_type == "intent.pause":
                    capability = provider.get_capability()
                    if not capability.can_pause:
                        raise RuntimeError(f"Provider {provider.name} does not support pause")
                    if not self._current_instance:
                        raise RuntimeError(f"Lease {self.lease_id} has no instance to pause")
                    try:
                        ok = provider.pause_session(self._current_instance.instance_id)
                    except Exception as exc:
                        raise RuntimeError(f"Failed to pause lease {self.lease_id}: {exc}") from exc
                    if not ok:
                        raise RuntimeError(f"Failed to pause lease {self.lease_id}")
                    self.desired_state = "paused"
                    self._set_observed_state("paused", reason="intent.pause")
                    self.status = "active"
                    self.last_error = None
                    self.needs_refresh = False
                    self.refresh_hint_at = None

                elif event_type == "intent.resume":
                    capability = provider.get_capability()
                    if not capability.can_resume:
                        raise RuntimeError(f"Provider {provider.name} does not support resume")
                    if not self._current_instance:
                        raise RuntimeError(f"Lease {self.lease_id} has no instance to resume")
                    try:
                        ok = provider.resume_session(self._current_instance.instance_id)
                    except Exception as exc:
                        raise RuntimeError(f"Failed to resume lease {self.lease_id}: {exc}") from exc
                    if not ok:
                        raise RuntimeError(f"Failed to resume lease {self.lease_id}")
                    self.desired_state = "running"
                    self._set_observed_state("running", reason="intent.resume")
                    self.status = "active"
                    self.last_error = None
                    self.needs_refresh = False
                    self.refresh_hint_at = None

                elif event_type == "intent.destroy":
                    capability = provider.get_capability()
                    if not capability.can_destroy:
                        raise RuntimeError(f"Provider {provider.name} does not support destroy")
                    if self._current_instance:
                        try:
                            ok = provider.destroy_session(self._current_instance.instance_id)
                        except Exception as exc:
                            raise RuntimeError(f"Failed to destroy lease {self.lease_id}: {exc}") from exc
                        if not ok:
                            raise RuntimeError(f"Failed to destroy lease {self.lease_id}")
                    self.desired_state = "destroyed"
                    self._set_observed_state("detached", reason="intent.destroy")
                    self.status = "expired"
                    self.last_error = None
                    self.needs_refresh = False
                    self.refresh_hint_at = None

                elif event_type == "intent.ensure_running":
                    if not self._current_instance:
                        raise RuntimeError(f"Lease {self.lease_id}: intent.ensure_running requires bound instance")
                    self.desired_state = "running"
                    self._set_observed_state("running", reason="intent.ensure_running")
                    self.status = "active"
                    self.last_error = None
                    self.needs_refresh = False
                    self.refresh_hint_at = None

                elif event_type == "observe.status":
                    raw = str(payload.get("status") or payload.get("observed_state") or "unknown")
                    observed = self._normalize_provider_state(raw)
                    self._set_observed_state(observed, reason="observe.status")
                    self.status = "expired" if observed == "detached" else "active"
                    self.last_error = None
                    self.needs_refresh = False
                    self.refresh_hint_at = None

                elif event_type == "provider.error":
                    self.last_error = str(payload.get("error") or "provider error")[:500]
                    self.needs_refresh = True
                    self.refresh_hint_at = now

                else:
                    raise RuntimeError(f"Unsupported lease event type: {event_type}")

                self.observed_at = now
                self.version += 1
                with _connect(self.db_path) as conn:
                    detached_persisted = self._persist_snapshot(conn=conn)
                    self._append_event(
                        event_type=event_type,
                        source=source,
                        payload=payload,
                        error=None,
                        event_id=eid,
                        conn=conn,
                    )
                    conn.commit()
                if detached_persisted:
                    self._detached_instance = None

            except Exception as exc:
                error = str(exc)
                self.last_error = error[:500]
                self.needs_refresh = True
                self.refresh_hint_at = datetime.now()
                self.observed_at = datetime.now()
                self.version += 1
                with _connect(self.db_path) as conn:
                    self._persist_lease_metadata(conn=conn)
                    self._append_event(
                        event_type=event_type,
                        source=source,
                        payload=payload,
                        error=error,
                        event_id=eid,
                        conn=conn,
                    )
                    conn.commit()
                raise

            return self._snapshot()

    def ensure_active_instance(self, provider: SandboxProvider) -> SandboxInstance:
        capability = provider.get_capability()
        if self._current_instance and self.observed_state == "running" and self._is_fresh() and not self.needs_refresh:
            return self._current_instance

        def _resolve_no_probe_instance() -> SandboxInstance | None:
            if not self._current_instance:
                return None
            if self.observed_state == "paused":
                raise RuntimeError(f"Sandbox lease {self.lease_id} is paused. Resume before executing commands.")
            if self.observed_state == "running" and not self.needs_refresh:
                return self._current_instance
            self._current_instance = None
            return None

        if self._current_instance:
            if not capability.supports_status_probe:
                resolved = _resolve_no_probe_instance()
                if resolved:
                    return resolved
            try:
                status = provider.get_session_status(self._current_instance.instance_id)
                self.apply(
                    provider,
                    event_type="observe.status",
                    source="run.refresh",
                    payload={"status": status},
                )
                if self.observed_state == "running" and self._current_instance:
                    return self._current_instance
                if self.observed_state == "paused":
                    raise RuntimeError(f"Sandbox lease {self.lease_id} is paused. Resume before executing commands.")
            except RuntimeError:
                raise
            except Exception as exc:
                self._record_provider_error(str(exc))

        with self._instance_lock():
            refreshed = LeaseStore(db_path=self.db_path).get(self.lease_id)
            if isinstance(refreshed, SQLiteLease):
                self._sync_from(refreshed)

            if self._current_instance:
                if not capability.supports_status_probe:
                    resolved = _resolve_no_probe_instance()
                    if resolved:
                        return resolved
                try:
                    status = provider.get_session_status(self._current_instance.instance_id)
                    self.apply(
                        provider,
                        event_type="observe.status",
                        source="run.refresh_locked",
                        payload={"status": status},
                    )
                    if self.observed_state == "running" and self._current_instance:
                        return self._current_instance
                    if self.observed_state == "paused":
                        raise RuntimeError(
                            f"Sandbox lease {self.lease_id} is paused. Resume before executing commands."
                        )
                except RuntimeError:
                    raise
                except Exception as exc:
                    self._record_provider_error(str(exc))

            self.status = "recovering"
            self._persist_lease_metadata()
            from sandbox.thread_context import get_current_thread_id
            thread_id = get_current_thread_id()
            session_info = provider.create_session(context_id=f"leon-{self.lease_id}", thread_id=thread_id)
            self._current_instance = SandboxInstance(
                instance_id=session_info.session_id,
                provider_name=self.provider_name,
                status="running",
                created_at=datetime.now(),
            )
            self.apply(
                provider,
                event_type="intent.ensure_running",
                source="run.create",
                payload={"created": True, "instance_id": session_info.session_id},
            )
            from sandbox.resource_snapshot import probe_and_upsert_for_instance

            probe_result = probe_and_upsert_for_instance(
                lease_id=self.lease_id,
                provider_name=self.provider_name,
                observed_state=self.observed_state,
                probe_mode="create_running",
                provider=provider,
                instance_id=session_info.session_id,
                db_path=self.db_path,
            )
            if not probe_result["ok"]:
                # @@@create-probe-fail-loud - lease creation succeeds, but resource probe failure stays explicit.
                print(f"[lease:{self.lease_id}] create probe error: {probe_result['error']}")
            if not self._current_instance:
                raise RuntimeError(f"Lease {self.lease_id}: failed to bind created instance")
            return self._current_instance

    def destroy_instance(self, provider: SandboxProvider, *, source: str = "api") -> None:
        self.apply(provider, event_type="intent.destroy", source=source)

    def pause_instance(self, provider: SandboxProvider, *, source: str = "api") -> bool:
        self.apply(provider, event_type="intent.pause", source=source)
        return True

    def resume_instance(self, provider: SandboxProvider, *, source: str = "api") -> bool:
        self.apply(provider, event_type="intent.resume", source=source)
        return True

    def refresh_instance_status(
        self,
        provider: SandboxProvider,
        *,
        force: bool = False,
        max_age_sec: float = LEASE_FRESHNESS_TTL_SEC,
    ) -> str:
        capability = provider.get_capability()
        if self.needs_refresh:
            force = True

        if not self._current_instance:
            return "detached"

        if not capability.supports_status_probe:
            return self.observed_state

        if not force and self._is_fresh(max_age_sec):
            return self.observed_state

        try:
            status = provider.get_session_status(self._current_instance.instance_id)
            self.apply(
                provider,
                event_type="observe.status",
                source="read.status",
                payload={"status": status},
            )
        except Exception as exc:
            self.apply(
                provider,
                event_type="provider.error",
                source="read.status",
                payload={"error": str(exc)},
            )
        return self.observed_state

    def mark_needs_refresh(self, hint_at: datetime | None = None) -> None:
        self.needs_refresh = True
        self.refresh_hint_at = hint_at or datetime.now()
        self.version += 1
        self._persist_lease_metadata()


class LeaseStore:
    """Store for managing SandboxLease persistence."""

    def __init__(self, db_path: Path = DEFAULT_DB_PATH, repository: SandboxRepositoryProtocol | None = None):
        self.db_path = db_path
        self._repo = repository  # @@@repository-migration - optional injection
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        with _connect(self.db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sandbox_leases (
                    lease_id TEXT PRIMARY KEY,
                    provider_name TEXT NOT NULL,
                    workspace_key TEXT,
                    current_instance_id TEXT,
                    instance_created_at TIMESTAMP,
                    desired_state TEXT NOT NULL DEFAULT 'running',
                    observed_state TEXT NOT NULL DEFAULT 'detached',
                    instance_status TEXT NOT NULL DEFAULT 'detached',
                    version INTEGER NOT NULL DEFAULT 0,
                    observed_at TIMESTAMP,
                    last_error TEXT,
                    needs_refresh INTEGER NOT NULL DEFAULT 0,
                    refresh_hint_at TIMESTAMP,
                    status TEXT DEFAULT 'active',
                    volume_id TEXT,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sandbox_instances (
                    instance_id TEXT PRIMARY KEY,
                    lease_id TEXT NOT NULL,
                    provider_session_id TEXT NOT NULL,
                    status TEXT DEFAULT 'running',
                    created_at TIMESTAMP NOT NULL,
                    last_seen_at TIMESTAMP NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS lease_events (
                    event_id TEXT PRIMARY KEY,
                    lease_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    source TEXT NOT NULL,
                    payload_json TEXT,
                    error TEXT,
                    created_at TIMESTAMP NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_lease_events_lease_created
                ON lease_events(lease_id, created_at DESC)
                """
            )
            conn.commit()
            lease_cols = {row[1] for row in conn.execute("PRAGMA table_info(sandbox_leases)").fetchall()}
            if "instance_status" not in lease_cols:
                # @@@lease-instance-status-compat - keep legacy readers alive while observed_state stays canonical.
                conn.execute(
                    "ALTER TABLE sandbox_leases ADD COLUMN instance_status TEXT NOT NULL DEFAULT 'detached'"
                )
                conn.execute("UPDATE sandbox_leases SET instance_status = observed_state")
                conn.commit()
                lease_cols = {row[1] for row in conn.execute("PRAGMA table_info(sandbox_leases)").fetchall()}
            if "volume_id" not in lease_cols:
                conn.execute("ALTER TABLE sandbox_leases ADD COLUMN volume_id TEXT")
                conn.commit()
                lease_cols = {row[1] for row in conn.execute("PRAGMA table_info(sandbox_leases)").fetchall()}
            instance_cols = {row[1] for row in conn.execute("PRAGMA table_info(sandbox_instances)").fetchall()}
            event_cols = {row[1] for row in conn.execute("PRAGMA table_info(lease_events)").fetchall()}

        missing_lease = REQUIRED_LEASE_COLUMNS - lease_cols
        if missing_lease:
            raise RuntimeError(
                f"sandbox_leases schema mismatch: missing {sorted(missing_lease)}. Purge ~/.leon/sandbox.db and retry."
            )
        missing_instances = REQUIRED_INSTANCE_COLUMNS - instance_cols
        if missing_instances:
            raise RuntimeError(
                f"sandbox_instances schema mismatch: missing {sorted(missing_instances)}. Purge ~/.leon/sandbox.db and retry."
            )
        missing_events = REQUIRED_EVENT_COLUMNS - event_cols
        if missing_events:
            raise RuntimeError(
                f"lease_events schema mismatch: missing {sorted(missing_events)}. Purge ~/.leon/sandbox.db and retry."
            )

    def get(self, lease_id: str) -> SandboxLease | None:
        # @@@repository-migration - use repository if available
        if self._repo:
            row = self._repo.get_lease(lease_id)
            if not row:
                return None

            instance = None
            if row["current_instance_id"]:
                created_raw = row["instance_created_at"] or datetime.now().isoformat()
                instance = SandboxInstance(
                    instance_id=row["current_instance_id"],
                    provider_name=row["provider_name"],
                    status=row["observed_state"] or "unknown",
                    created_at=datetime.fromisoformat(created_raw),
                )

            return SQLiteLease(
                lease_id=row["lease_id"],
                provider_name=row["provider_name"],
                current_instance=instance,
                db_path=self.db_path,
                status=row["status"] or "active",
                workspace_key=row["workspace_key"],
                desired_state=row["desired_state"] or "running",
                observed_state=row["observed_state"] or "detached",
                version=int(row["version"] or 0),
                observed_at=datetime.fromisoformat(row["observed_at"]) if row["observed_at"] else None,
                last_error=row["last_error"],
                needs_refresh=bool(row["needs_refresh"]),
                refresh_hint_at=datetime.fromisoformat(row["refresh_hint_at"]) if row["refresh_hint_at"] else None,
                volume_id=row.get("volume_id"),
            )

        # Fallback to inline SQL
        with _connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT lease_id,
                       provider_name,
                       workspace_key,
                       current_instance_id,
                       instance_created_at,
                       desired_state,
                       observed_state,
                       version,
                       observed_at,
                       last_error,
                       needs_refresh,
                       refresh_hint_at,
                       status,
                       volume_id
                FROM sandbox_leases
                WHERE lease_id = ?
                """,
                (lease_id,),
            ).fetchone()

            if not row:
                return None

            instance = None
            if row["current_instance_id"]:
                created_raw = row["instance_created_at"] or datetime.now().isoformat()
                instance = SandboxInstance(
                    instance_id=row["current_instance_id"],
                    provider_name=row["provider_name"],
                    status=row["observed_state"] or "unknown",
                    created_at=datetime.fromisoformat(created_raw),
                )

            return SQLiteLease(
                lease_id=row["lease_id"],
                provider_name=row["provider_name"],
                current_instance=instance,
                db_path=self.db_path,
                status=row["status"] or "active",
                workspace_key=row["workspace_key"],
                desired_state=row["desired_state"] or "running",
                observed_state=row["observed_state"] or "detached",
                version=int(row["version"] or 0),
                observed_at=datetime.fromisoformat(row["observed_at"]) if row["observed_at"] else None,
                last_error=row["last_error"],
                needs_refresh=bool(row["needs_refresh"]),
                refresh_hint_at=datetime.fromisoformat(row["refresh_hint_at"]) if row["refresh_hint_at"] else None,
                volume_id=row["volume_id"],
            )

    def create(self, lease_id: str, provider_name: str, volume_id: str | None = None) -> SandboxLease:
        now = datetime.now().isoformat()

        # @@@repository-migration - use repository if available
        if self._repo:
            self._repo.upsert_lease(
                lease_id=lease_id,
                provider_name=provider_name,
                workspace_key=None,
                current_instance_id=None,
                instance_created_at=None,
                desired_state="running",
                observed_state="detached",
                version=0,
                observed_at=now,
                last_error=None,
                needs_refresh=0,
                refresh_hint_at=None,
                status="active",
                created_at=now,
                updated_at=now,
            )
        else:
            with _connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO sandbox_leases (
                        lease_id,
                        provider_name,
                        desired_state,
                        observed_state,
                        instance_status,
                        version,
                        observed_at,
                        last_error,
                        needs_refresh,
                        refresh_hint_at,
                        status,
                        volume_id,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        lease_id,
                        provider_name,
                        "running",
                        "detached",
                        "detached",
                        0,
                        now,
                        None,
                        0,
                        None,
                        "active",
                        volume_id,
                        now,
                        now,
                    ),
                )
                conn.commit()

        return SQLiteLease(
            lease_id=lease_id,
            provider_name=provider_name,
            current_instance=None,
            db_path=self.db_path,
            status="active",
            desired_state="running",
            observed_state="detached",
            version=0,
            observed_at=datetime.fromisoformat(now),
            last_error=None,
            needs_refresh=False,
            refresh_hint_at=None,
            volume_id=volume_id,
        )

    def find_by_instance(self, *, provider_name: str, instance_id: str) -> SandboxLease | None:
        # @@@repository-migration - use repository if available
        if self._repo:
            row = self._repo.find_lease_by_instance(provider_name, instance_id)
            if not row:
                return None
            return self.get(row["lease_id"])

        # Fallback to inline SQL
        with _connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT lease_id
                FROM sandbox_leases
                WHERE provider_name = ? AND current_instance_id = ?
                LIMIT 1
                """,
                (provider_name, instance_id),
            ).fetchone()
            if not row:
                return None
            return self.get(row["lease_id"])

    def adopt_instance(
        self,
        *,
        lease_id: str,
        provider_name: str,
        instance_id: str,
        status: str = "unknown",
    ) -> SandboxLease:
        lease = self.get(lease_id)
        if lease is None:
            lease = self.create(lease_id=lease_id, provider_name=provider_name)
        if lease.provider_name != provider_name:
            raise RuntimeError(
                f"Lease provider mismatch during adopt: lease={lease.provider_name}, requested={provider_name}"
            )

        now = datetime.now().isoformat()
        normalized = parse_lease_instance_state(status).value
        desired = "paused" if normalized == "paused" else "running"
        with _connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE sandbox_leases
                SET current_instance_id = ?,
                    instance_created_at = ?,
                    desired_state = ?,
                    observed_state = ?,
                    instance_status = ?,
                    version = version + 1,
                    observed_at = ?,
                    last_error = ?,
                    needs_refresh = ?,
                    refresh_hint_at = ?,
                    status = ?,
                    updated_at = ?
                WHERE lease_id = ?
                """,
                (
                    instance_id,
                    now,
                    desired,
                    normalized,
                    normalized,
                    now,
                    None,
                    1,
                    now,
                    "active",
                    now,
                    lease_id,
                ),
            )
            conn.execute(
                """
                INSERT INTO sandbox_instances (
                    instance_id, lease_id, provider_session_id, status, created_at, last_seen_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(instance_id) DO UPDATE SET
                    lease_id = excluded.lease_id,
                    status = excluded.status,
                    last_seen_at = excluded.last_seen_at
                """,
                (
                    instance_id,
                    lease_id,
                    instance_id,
                    normalized,
                    now,
                    now,
                ),
            )
            conn.execute(
                """
                INSERT INTO lease_events (event_id, lease_id, event_type, source, payload_json, error, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"evt-{uuid.uuid4().hex}",
                    lease_id,
                    "observe.status",
                    "adopt",
                    json.dumps({"status": normalized, "instance_id": instance_id}),
                    None,
                    now,
                ),
            )
            conn.commit()

        adopted = self.get(lease_id)
        if adopted is None:
            raise RuntimeError(f"Failed to load adopted lease: {lease_id}")
        return adopted

    def mark_needs_refresh(self, *, lease_id: str, hint_at: datetime | None = None) -> bool:
        hinted_at = (hint_at or datetime.now()).isoformat()
        with _connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                UPDATE sandbox_leases
                SET needs_refresh = 1,
                    refresh_hint_at = ?,
                    version = version + 1,
                    updated_at = ?
                WHERE lease_id = ?
                """,
                (hinted_at, datetime.now().isoformat(), lease_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def delete(self, lease_id: str) -> None:
        # @@@repository-migration - use repository if available
        if self._repo:
            self._repo.delete_lease(lease_id)
        else:
            with _connect(self.db_path) as conn:
                conn.execute("DELETE FROM sandbox_instances WHERE lease_id = ?", (lease_id,))
                conn.execute("DELETE FROM lease_events WHERE lease_id = ?", (lease_id,))
                conn.execute("DELETE FROM lease_resource_snapshots WHERE lease_id = ?", (lease_id,))
                conn.execute("DELETE FROM sandbox_leases WHERE lease_id = ?", (lease_id,))
                conn.commit()
        with SQLiteLease._lock_guard:
            SQLiteLease._lease_locks.pop(lease_id, None)

    def list_all(self) -> list[dict]:
        # @@@repository-migration - use repository if available
        if self._repo:
            return self._repo.list_all_leases()

        # Fallback to inline SQL
        with _connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT lease_id,
                       provider_name,
                       current_instance_id,
                       desired_state,
                       observed_state,
                       version,
                       created_at,
                       updated_at
                FROM sandbox_leases
                ORDER BY created_at DESC
                """
            ).fetchall()
            return [dict(row) for row in rows]

    def list_by_provider(self, provider_name: str) -> list[dict]:
        # @@@repository-migration - use repository if available
        if self._repo:
            return self._repo.list_leases_by_provider(provider_name)

        # Fallback to inline SQL
        with _connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT lease_id,
                       provider_name,
                       current_instance_id,
                       desired_state,
                       observed_state,
                       version,
                       created_at,
                       updated_at
                FROM sandbox_leases
                WHERE provider_name = ?
                ORDER BY created_at DESC
                """,
                (provider_name,),
            ).fetchall()
            return [dict(row) for row in rows]
