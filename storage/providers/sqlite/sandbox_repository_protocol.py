"""Repository protocol for sandbox persistence.

This protocol defines the contract that both legacy and new implementations must satisfy.
Using Protocol (structural subtyping) allows gradual migration without inheritance.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from sandbox.config import DEFAULT_DB_PATH


class SandboxRepositoryProtocol(Protocol):
    """Protocol for sandbox persistence operations.

    Both LegacySandboxRepository (wrapping existing SQL) and SandboxRepository
    (new implementation) must conform to this protocol.
    """

    db_path: Path

    # === LEASE OPERATIONS ===

    def upsert_lease(
        self,
        lease_id: str,
        provider_name: str,
        workspace_key: str | None,
        current_instance_id: str | None,
        instance_created_at: str | None,
        desired_state: str,
        observed_state: str,
        version: int,
        observed_at: str | None,
        last_error: str | None,
        needs_refresh: int,
        refresh_hint_at: str | None,
        status: str,
        created_at: str,
        updated_at: str,
    ) -> None:
        """Insert or update lease snapshot."""
        ...

    def update_lease_state(
        self,
        lease_id: str,
        observed_state: str,
        version: int,
        observed_at: str,
        last_error: str | None = None,
    ) -> None:
        """Update lease observed state."""
        ...

    def get_lease(self, lease_id: str) -> dict[str, Any] | None:
        """Get lease by ID."""
        ...

    def delete_lease(self, lease_id: str) -> None:
        """Delete lease."""
        ...

    def find_lease_by_instance(self, provider_name: str, instance_id: str) -> dict[str, Any] | None:
        """Find lease by provider and instance ID."""
        ...

    def list_all_leases(self) -> list[dict[str, Any]]:
        """List all leases with summary info."""
        ...

    def list_leases_by_provider(self, provider_name: str) -> list[dict[str, Any]]:
        """List leases for a specific provider."""
        ...

    # === INSTANCE OPERATIONS ===

    def upsert_instance(
        self,
        instance_id: str,
        lease_id: str,
        provider_session_id: str,
        status: str,
        created_at: str,
        last_seen_at: str,
    ) -> None:
        """Insert or update instance."""
        ...

    def update_instance_last_seen(self, instance_id: str, last_seen_at: str) -> None:
        """Update instance last_seen_at."""
        ...

    # === TERMINAL OPERATIONS ===

    def upsert_terminal(
        self,
        terminal_id: str,
        thread_id: str,
        lease_id: str,
        cwd: str,
        env_delta_json: str,
        state_version: int,
        created_at: str,
        updated_at: str,
    ) -> None:
        """Insert or update terminal."""
        ...

    def update_terminal_state(
        self,
        terminal_id: str,
        cwd: str,
        env_delta_json: str,
        state_version: int,
        updated_at: str,
    ) -> None:
        """Update terminal state."""
        ...

    def get_terminal(self, terminal_id: str) -> dict[str, Any] | None:
        """Get terminal by ID."""
        ...

    def list_terminals_by_thread(self, thread_id: str) -> list[dict[str, Any]]:
        """List terminals for thread."""
        ...

    def delete_terminal(self, terminal_id: str) -> None:
        """Delete terminal and related commands."""
        ...

    # === TERMINAL POINTER OPERATIONS ===

    def upsert_terminal_pointer(
        self,
        thread_id: str,
        active_terminal_id: str,
        default_terminal_id: str,
        updated_at: str,
    ) -> None:
        """Insert or update terminal pointer."""
        ...

    def get_terminal_pointer(self, thread_id: str) -> dict[str, Any] | None:
        """Get terminal pointer for thread."""
        ...

    def update_terminal_pointer_active(
        self, thread_id: str, active_terminal_id: str, updated_at: str
    ) -> None:
        """Update active terminal."""
        ...

    def delete_terminal_pointer(self, thread_id: str) -> None:
        """Delete terminal pointer."""
        ...

    # === SESSION OPERATIONS ===

    def upsert_session(
        self,
        chat_session_id: str,
        thread_id: str,
        terminal_id: str,
        lease_id: str,
        runtime_id: str | None,
        status: str,
        idle_ttl_sec: int,
        max_duration_sec: int,
        budget_json: str | None,
        started_at: str,
        last_active_at: str,
        ended_at: str | None,
        close_reason: str | None,
    ) -> None:
        """Insert or update session."""
        ...

    def update_session_status(
        self, chat_session_id: str, status: str, updated_at: str
    ) -> None:
        """Update session status."""
        ...

    def update_session_activity(
        self, chat_session_id: str, last_active_at: str
    ) -> None:
        """Update session last_active_at."""
        ...

    def update_session_close(
        self, chat_session_id: str, status: str, ended_at: str, close_reason: str
    ) -> None:
        """Close session."""
        ...

    def get_session(self, chat_session_id: str) -> dict[str, Any] | None:
        """Get session by ID."""
        ...

    # === EVENT OPERATIONS ===

    def insert_lease_event(
        self,
        event_id: str,
        lease_id: str,
        event_type: str,
        source: str,
        payload_json: str | None,
        error: str | None,
        created_at: str,
    ) -> None:
        """Insert lease event."""
        ...

    def insert_provider_event(
        self,
        provider_name: str,
        instance_id: str,
        event_type: str,
        payload_json: str | None,
        matched_lease_id: str | None,
        created_at: str,
    ) -> None:
        """Insert provider event."""
        ...

    # === TABLE MANAGEMENT ===

    def ensure_tables(self) -> None:
        """Create all tables if they don't exist."""
        ...
