"""Contract tests for SandboxRepository implementation.

These tests define the repository contract that the implementation must satisfy.
"""

from __future__ import annotations

import pytest
from pathlib import Path
from datetime import datetime, timezone

from storage.providers.sqlite.sandbox_repo import SandboxRepository


@pytest.fixture
def repository(tmp_path):
    """Fixture providing repository instance."""
    db_path = tmp_path / "test.db"
    return SandboxRepository(db_path)


def _now_iso() -> str:
    """Helper for consistent timestamps."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# === LEASE CONTRACT TESTS ===

class TestLeaseContract:
    """Contract tests for lease operations."""

    def test_upsert_lease_creates_new(self, repository):
        """Both implementations must create new lease identically."""
        repository.ensure_tables()

        now = _now_iso()
        repository.upsert_lease(
            lease_id="lease-1",
            provider_name="docker",
            workspace_key=None,
            current_instance_id=None,
            instance_created_at=None,
            desired_state="running",
            observed_state="detached",
            version=0,
            observed_at=None,
            last_error=None,
            needs_refresh=0,
            refresh_hint_at=None,
            status="active",
            created_at=now,
            updated_at=now,
        )

        lease = repository.get_lease("lease-1")
        assert lease is not None
        assert lease["lease_id"] == "lease-1"
        assert lease["provider_name"] == "docker"
        assert lease["desired_state"] == "running"

    def test_upsert_lease_updates_existing(self, repository):
        """Both implementations must update existing lease identically."""
        repository.ensure_tables()

        now = _now_iso()
        # Create
        repository.upsert_lease(
            lease_id="lease-1",
            provider_name="docker",
            workspace_key=None,
            current_instance_id=None,
            instance_created_at=None,
            desired_state="running",
            observed_state="detached",
            version=0,
            observed_at=None,
            last_error=None,
            needs_refresh=0,
            refresh_hint_at=None,
            status="active",
            created_at=now,
            updated_at=now,
        )

        # Update
        repository.update_lease_state(
            lease_id="lease-1",
            observed_state="running",
            version=1,
            observed_at=now,
            last_error=None,
        )

        lease = repository.get_lease("lease-1")
        assert lease["observed_state"] == "running"
        assert lease["version"] == 1

    def test_delete_lease(self, repository):
        """Both implementations must delete lease identically."""
        repository.ensure_tables()

        now = _now_iso()
        repository.upsert_lease(
            lease_id="lease-1",
            provider_name="docker",
            workspace_key=None,
            current_instance_id=None,
            instance_created_at=None,
            desired_state="running",
            observed_state="detached",
            version=0,
            observed_at=None,
            last_error=None,
            needs_refresh=0,
            refresh_hint_at=None,
            status="active",
            created_at=now,
            updated_at=now,
        )

        repository.delete_lease("lease-1")

        lease = repository.get_lease("lease-1")
        assert lease is None


# === TERMINAL CONTRACT TESTS ===

class TestTerminalContract:
    """Contract tests for terminal operations."""

    def test_upsert_terminal_creates_new(self, repository):
        """Both implementations must create new terminal identically."""
        repository.ensure_tables()

        now = _now_iso()
        repository.upsert_terminal(
            terminal_id="term-1",
            thread_id="thread-1",
            lease_id="lease-1",
            cwd="/home",
            env_delta_json="{}",
            state_version=0,
            created_at=now,
            updated_at=now,
        )

        terminal = repository.get_terminal("term-1")
        assert terminal is not None
        assert terminal["terminal_id"] == "term-1"
        assert terminal["cwd"] == "/home"

    def test_update_terminal_state(self, repository):
        """Both implementations must update terminal state identically."""
        repository.ensure_tables()

        now = _now_iso()
        repository.upsert_terminal(
            terminal_id="term-1",
            thread_id="thread-1",
            lease_id="lease-1",
            cwd="/home",
            env_delta_json="{}",
            state_version=0,
            created_at=now,
            updated_at=now,
        )

        repository.update_terminal_state(
            terminal_id="term-1",
            cwd="/workspace",
            env_delta_json='{"PATH": "/usr/bin"}',
            state_version=1,
            updated_at=now,
        )

        terminal = repository.get_terminal("term-1")
        assert terminal["cwd"] == "/workspace"
        assert terminal["state_version"] == 1


# === SESSION CONTRACT TESTS ===

class TestSessionContract:
    """Contract tests for session operations."""

    def test_upsert_session_creates_new(self, repository):
        """Both implementations must create new session identically."""
        repository.ensure_tables()

        now = _now_iso()
        repository.upsert_session(
            chat_session_id="session-1",
            thread_id="thread-1",
            terminal_id="term-1",
            lease_id="lease-1",
            runtime_id="runtime-1",
            status="active",
            idle_ttl_sec=300,
            max_duration_sec=86400,
            budget_json=None,
            started_at=now,
            last_active_at=now,
            ended_at=None,
            close_reason=None,
        )

        session = repository.get_session("session-1")
        assert session is not None
        assert session["chat_session_id"] == "session-1"
        assert session["status"] == "active"

    def test_update_session_status(self, repository):
        """Both implementations must update session status identically."""
        repository.ensure_tables()

        now = _now_iso()
        repository.upsert_session(
            chat_session_id="session-1",
            thread_id="thread-1",
            terminal_id="term-1",
            lease_id="lease-1",
            runtime_id="runtime-1",
            status="active",
            idle_ttl_sec=300,
            max_duration_sec=86400,
            budget_json=None,
            started_at=now,
            last_active_at=now,
            ended_at=None,
            close_reason=None,
        )

        repository.update_session_status(
            chat_session_id="session-1",
            status="closed",
            updated_at=now,
        )

        session = repository.get_session("session-1")
        assert session["status"] == "closed"


# === EVENT CONTRACT TESTS ===

class TestEventContract:
    """Contract tests for event operations."""

    def test_insert_lease_event(self, repository):
        """Both implementations must insert lease event identically."""
        repository.ensure_tables()

        now = _now_iso()
        repository.insert_lease_event(
            event_id="event-1",
            lease_id="lease-1",
            event_type="state_change",
            source="lifecycle",
            payload_json='{"from": "detached", "to": "running"}',
            error=None,
            created_at=now,
        )

        # No get_lease_event in protocol, but ensure no exception

    def test_insert_provider_event(self, repository):
        """Both implementations must insert provider event identically."""
        repository.ensure_tables()

        now = _now_iso()
        repository.insert_provider_event(
            provider_name="docker",
            instance_id="inst-1",
            event_type="container.start",
            payload_json='{"container_id": "abc123"}',
            matched_lease_id="lease-1",
            created_at=now,
        )

        # No get_provider_event in protocol, but ensure no exception
