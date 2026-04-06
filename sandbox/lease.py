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

from sandbox.lifecycle import (
    LeaseInstanceState,
    assert_lease_instance_transition,
    parse_lease_instance_state,
)
from storage.providers.sqlite.kernel import SQLiteDBRole, connect_sqlite, resolve_role_db_path

if TYPE_CHECKING:
    from sandbox.provider import SandboxProvider

LEASE_FRESHNESS_TTL_SEC = 3.0

REQUIRED_LEASE_COLUMNS = {
    "lease_id",
    "provider_name",
    "recipe_id",
    "recipe_json",
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
        recipe_id: str | None = None,
        recipe: dict[str, Any] | None = None,
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
        bind_mounts: list[dict[str, str]] | None = None,
    ):
        self.lease_id = lease_id
        self.provider_name = provider_name
        self.recipe = recipe
        self.recipe_id = recipe_id or (str(recipe.get("id")) if isinstance(recipe, dict) and recipe.get("id") else None)
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
        self.bind_mounts = bind_mounts

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
        recipe_id: str | None = None,
        recipe: dict[str, Any] | None = None,
        current_instance: SandboxInstance | None = None,
        db_path: Path | None = None,
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
            recipe_id=recipe_id,
            recipe=recipe,
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
        self.db_path = db_path or resolve_role_db_path(SQLiteDBRole.SANDBOX)
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
            raise RuntimeError(f"Lease {self.lease_id}: cannot set observed={observed} without bound instance ({reason})")

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
                    recipe_id = ?,
                    recipe_json = ?,
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
                    self.recipe_id,
                    json.dumps(self.recipe, ensure_ascii=False) if self.recipe is not None else None,
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
                SET recipe_id = ?,
                    recipe_json = ?,
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
                    self.recipe_id,
                    json.dumps(self.recipe, ensure_ascii=False) if self.recipe is not None else None,
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
        self.recipe = other.recipe
        self.recipe_id = other.recipe_id
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
                from storage.providers.sqlite.lease_repo import SQLiteLeaseRepo

                _repo = SQLiteLeaseRepo(db_path=self.db_path)
                try:
                    _row = _repo.get(self.lease_id)
                finally:
                    _repo.close()
                if _row:
                    self._sync_from(lease_from_row(_row, self.db_path))
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
            from storage.providers.sqlite.lease_repo import SQLiteLeaseRepo

            _repo = SQLiteLeaseRepo(db_path=self.db_path)
            try:
                _row = _repo.get(self.lease_id)
            finally:
                _repo.close()
            if _row:
                self._sync_from(lease_from_row(_row, self.db_path))

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
                        raise RuntimeError(f"Sandbox lease {self.lease_id} is paused. Resume before executing commands.")
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


def lease_from_row(row: dict, db_path: Path) -> SQLiteLease:
    """Construct SQLiteLease from a dict returned by the repo."""
    instance = None
    inst_data = row.get("_instance")
    if inst_data:
        instance = SandboxInstance(
            instance_id=inst_data["instance_id"],
            provider_name=row["provider_name"],
            status=inst_data.get("status", "unknown"),
            created_at=datetime.fromisoformat(str(inst_data["created_at"])),
        )
    elif row.get("current_instance_id"):
        instance = SandboxInstance(
            instance_id=row["current_instance_id"],
            provider_name=row["provider_name"],
            status=row.get("instance_status") or row.get("observed_state") or "unknown",
            created_at=datetime.fromisoformat(str(row["instance_created_at"])) if row.get("instance_created_at") else datetime.now(),
        )

    observed_at = None
    if row.get("observed_at"):
        observed_at = datetime.fromisoformat(str(row["observed_at"]))

    refresh_hint_at = None
    if row.get("refresh_hint_at"):
        refresh_hint_at = datetime.fromisoformat(str(row["refresh_hint_at"]))

    return SQLiteLease(
        lease_id=row["lease_id"],
        provider_name=row["provider_name"],
        recipe_id=row.get("recipe_id"),
        recipe=json.loads(str(row["recipe_json"])) if row.get("recipe_json") else None,
        current_instance=instance,
        db_path=db_path,
        status=row.get("status") or "active",
        workspace_key=row.get("workspace_key"),
        desired_state=row.get("desired_state") or "running",
        observed_state=row.get("observed_state") or "detached",
        version=int(row.get("version") or 0),
        observed_at=observed_at,
        last_error=row.get("last_error"),
        needs_refresh=bool(row.get("needs_refresh")),
        refresh_hint_at=refresh_hint_at,
        volume_id=row.get("volume_id"),
    )
