"""Shared storage domain models — provider-neutral data types."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


# ============================================================================
# Sandbox State Models
# ============================================================================


class LeaseObservedState(Enum):
    """Sandbox lease actual state (from provider).

    These are the actual states reported by sandbox providers.
    """
    RUNNING = "running"    # Running with bound instance
    DETACHED = "detached"  # Running but detached from terminal
    PAUSED = "paused"      # Paused
    # None means destroyed


class LeaseDesiredState(Enum):
    """Sandbox lease desired state (set by user/system)."""
    RUNNING = "running"
    PAUSED = "paused"
    DESTROYED = "destroyed"


class SessionDisplayStatus(Enum):
    """Frontend display status (unified contract).

    These are the status values that frontend expects and displays.
    """
    RUNNING = "running"      # Currently running
    PAUSED = "paused"        # Paused
    STOPPED = "stopped"      # Stopped/destroyed
    DESTROYING = "destroying"  # Being destroyed


def map_lease_to_session_status(
    observed_state: str | None,
    desired_state: str | None
) -> str:
    """Map sandbox lease state to frontend display status.

    Mapping rules:
    - observed="detached" → "stopped" (instance destroyed/no longer current)
    - observed="running" → "running"
    - observed="paused" → "paused"
    - observed=None → "stopped"
    - desired="destroyed" → "destroying"

    Args:
        observed_state: Actual state from provider ("running", "detached", "paused", or None)
        desired_state: Desired state ("running", "paused", "destroyed", or None)

    Returns:
        Display status string ("running", "paused", "stopped", or "destroying")
    """
    if not observed_state:
        return SessionDisplayStatus.STOPPED.value

    observed = observed_state.strip().lower()
    desired = (desired_state or "").strip().lower()

    # Being destroyed
    if desired == LeaseDesiredState.DESTROYED.value:
        return SessionDisplayStatus.DESTROYING.value

    # @@@detached-is-stopped - detached means instance is destroyed/stopped (current_instance_id=NULL)
    # parse_lease_instance_state() maps {"deleted", "dead", "stopped"} → DETACHED
    if observed == LeaseObservedState.DETACHED.value:
        return SessionDisplayStatus.STOPPED.value

    # Running — only "running" means the sandbox is up with bound instance
    if observed == LeaseObservedState.RUNNING.value:
        return SessionDisplayStatus.RUNNING.value

    # Paused
    if observed == LeaseObservedState.PAUSED.value:
        return SessionDisplayStatus.PAUSED.value

    # Unknown state, treat as stopped
    return SessionDisplayStatus.STOPPED.value


# ============================================================================
# File Operation Models
# ============================================================================


@dataclass
class FileOperationRow:
    id: str
    thread_id: str
    checkpoint_id: str
    timestamp: float
    operation_type: str
    file_path: str
    before_content: str | None
    after_content: str
    changes: list[dict] | None
    status: str = "applied"
