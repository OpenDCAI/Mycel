from __future__ import annotations

from enum import Enum


class SandboxObservedState(Enum):
    """Sandbox actual state reported by the provider.

    These are the actual states reported by sandbox providers.
    """

    RUNNING = "running"
    DETACHED = "detached"
    PAUSED = "paused"


class SandboxDesiredState(Enum):
    """Sandbox desired state set by user or system."""

    RUNNING = "running"
    PAUSED = "paused"
    DESTROYED = "destroyed"


class SandboxDisplayStatus(Enum):
    """Frontend sandbox display status.

    These are the status values that frontend expects and displays.
    """

    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    DESTROYING = "destroying"


def map_sandbox_state_to_display_status(observed_state: str | None, desired_state: str | None) -> str:
    """Map sandbox state to frontend display status.

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
        return SandboxDisplayStatus.STOPPED.value

    observed = observed_state.strip().lower()
    desired = (desired_state or "").strip().lower()

    if desired == SandboxDesiredState.DESTROYED.value:
        return SandboxDisplayStatus.DESTROYING.value

    if observed == SandboxObservedState.DETACHED.value:
        # @@@detached-inherits-desired-state - detached is a provider-side loss of binding, not
        # automatically a user-visible stop. Resource cards should keep showing intent until
        # the sandbox is actually destroyed.
        if desired == SandboxDesiredState.RUNNING.value:
            return SandboxDisplayStatus.RUNNING.value
        if desired == SandboxDesiredState.PAUSED.value:
            return SandboxDisplayStatus.PAUSED.value
        return SandboxDisplayStatus.STOPPED.value

    if observed == SandboxObservedState.RUNNING.value:
        return SandboxDisplayStatus.RUNNING.value

    if observed == SandboxObservedState.PAUSED.value:
        return SandboxDisplayStatus.PAUSED.value

    return SandboxDisplayStatus.STOPPED.value
