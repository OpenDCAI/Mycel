"""Shared storage domain models — provider-neutral data types."""

from __future__ import annotations

from enum import Enum

# ============================================================================
# Sandbox State Models
# ============================================================================


class LeaseObservedState(Enum):
    """Sandbox lease actual state (from provider).

    These are the actual states reported by sandbox providers.
    """

    RUNNING = "running"  # Running with bound instance
    DETACHED = "detached"  # Running but detached from terminal
    PAUSED = "paused"  # Paused
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

    RUNNING = "running"  # Currently running
    PAUSED = "paused"  # Paused
    STOPPED = "stopped"  # Stopped/destroyed
    DESTROYING = "destroying"  # Being destroyed


def map_lease_to_session_status(observed_state: str | None, desired_state: str | None) -> str:
    """Map sandbox lease state to frontend display status.

    Mapping rules:
    - observed="detached" + desired="running" → "running"
    - observed="detached" + desired="paused" → "paused"
    - observed="detached" + desired missing/other → "stopped"
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

    if observed == LeaseObservedState.DETACHED.value:
        # @@@detached-inherits-desired-state - detached is a provider-side loss of binding, not
        # automatically a user-visible stop. Resource cards should keep showing the operator's
        # intended running/paused state until the lease is actually destroyed.
        if desired == LeaseDesiredState.RUNNING.value:
            return SessionDisplayStatus.RUNNING.value
        if desired == LeaseDesiredState.PAUSED.value:
            return SessionDisplayStatus.PAUSED.value
        return SessionDisplayStatus.STOPPED.value

    # Running — only "running" means the sandbox is up with bound instance
    if observed == LeaseObservedState.RUNNING.value:
        return SessionDisplayStatus.RUNNING.value

    # Paused
    if observed == LeaseObservedState.PAUSED.value:
        return SessionDisplayStatus.PAUSED.value

    # Unknown state, treat as stopped
    return SessionDisplayStatus.STOPPED.value
