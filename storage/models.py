from __future__ import annotations

from enum import Enum


class SandboxObservedState(Enum):
    RUNNING = "running"
    DETACHED = "detached"
    PAUSED = "paused"


class SandboxDesiredState(Enum):
    RUNNING = "running"
    PAUSED = "paused"
    DESTROYED = "destroyed"


class SandboxDisplayStatus(Enum):
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    DESTROYING = "destroying"


def map_sandbox_state_to_display_status(observed_state: str | None, desired_state: str | None) -> str:
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
