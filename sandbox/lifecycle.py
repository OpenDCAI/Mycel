"""Lifecycle state machine contracts for chat sessions and sandbox runtime instances.

Fail-loud policy:
- Invalid state strings raise immediately.
- Illegal transitions raise immediately.
"""

from __future__ import annotations

from enum import StrEnum


class ChatSessionState(StrEnum):
    ACTIVE = "active"
    IDLE = "idle"
    PAUSED = "paused"
    CLOSED = "closed"
    FAILED = "failed"


class SandboxRuntimeInstanceState(StrEnum):
    RUNNING = "running"
    PAUSED = "paused"
    DETACHED = "detached"
    UNKNOWN = "unknown"


def parse_chat_session_state(value: str | None) -> ChatSessionState:
    if value is None:
        raise RuntimeError("ChatSession state is required")
    try:
        return ChatSessionState(value)
    except ValueError as e:
        raise RuntimeError(f"Invalid ChatSession state: {value}") from e


def parse_sandbox_runtime_instance_state(value: str | None) -> SandboxRuntimeInstanceState:
    if value is None:
        return SandboxRuntimeInstanceState.DETACHED
    lowered = value.lower()
    if lowered in {"deleted", "dead", "stopped"}:
        return SandboxRuntimeInstanceState.DETACHED
    try:
        return SandboxRuntimeInstanceState(lowered)
    except ValueError as e:
        raise RuntimeError(f"Invalid SandboxRuntimeInstance state: {value}") from e


def assert_chat_session_transition(
    current: ChatSessionState | None,
    target: ChatSessionState,
    *,
    reason: str,
) -> None:
    if current is None:
        if target != ChatSessionState.ACTIVE:
            raise RuntimeError(f"Illegal chat session transition: <new> -> {target} ({reason})")
        return
    if current == target:
        return

    allowed: set[tuple[ChatSessionState, ChatSessionState]] = {
        (ChatSessionState.ACTIVE, ChatSessionState.IDLE),
        (ChatSessionState.ACTIVE, ChatSessionState.PAUSED),
        (ChatSessionState.ACTIVE, ChatSessionState.CLOSED),
        (ChatSessionState.ACTIVE, ChatSessionState.FAILED),
        (ChatSessionState.IDLE, ChatSessionState.ACTIVE),
        (ChatSessionState.IDLE, ChatSessionState.PAUSED),
        (ChatSessionState.IDLE, ChatSessionState.CLOSED),
        (ChatSessionState.IDLE, ChatSessionState.FAILED),
        (ChatSessionState.PAUSED, ChatSessionState.ACTIVE),
        (ChatSessionState.PAUSED, ChatSessionState.CLOSED),
        (ChatSessionState.PAUSED, ChatSessionState.FAILED),
        (ChatSessionState.FAILED, ChatSessionState.CLOSED),
    }
    if (current, target) not in allowed:
        raise RuntimeError(f"Illegal chat session transition: {current} -> {target} ({reason})")


def assert_sandbox_runtime_instance_transition(
    current: SandboxRuntimeInstanceState | None,
    target: SandboxRuntimeInstanceState,
    *,
    reason: str,
) -> None:
    if current is None:
        current = SandboxRuntimeInstanceState.DETACHED
    if current == target:
        return

    allowed: set[tuple[SandboxRuntimeInstanceState, SandboxRuntimeInstanceState]] = {
        (SandboxRuntimeInstanceState.DETACHED, SandboxRuntimeInstanceState.RUNNING),
        (SandboxRuntimeInstanceState.DETACHED, SandboxRuntimeInstanceState.UNKNOWN),
        (SandboxRuntimeInstanceState.RUNNING, SandboxRuntimeInstanceState.PAUSED),
        (SandboxRuntimeInstanceState.RUNNING, SandboxRuntimeInstanceState.DETACHED),
        (SandboxRuntimeInstanceState.RUNNING, SandboxRuntimeInstanceState.UNKNOWN),
        (SandboxRuntimeInstanceState.PAUSED, SandboxRuntimeInstanceState.RUNNING),
        (SandboxRuntimeInstanceState.PAUSED, SandboxRuntimeInstanceState.DETACHED),
        (SandboxRuntimeInstanceState.PAUSED, SandboxRuntimeInstanceState.UNKNOWN),
        (SandboxRuntimeInstanceState.UNKNOWN, SandboxRuntimeInstanceState.RUNNING),
        (SandboxRuntimeInstanceState.UNKNOWN, SandboxRuntimeInstanceState.PAUSED),
        (SandboxRuntimeInstanceState.UNKNOWN, SandboxRuntimeInstanceState.DETACHED),
    }
    if (current, target) not in allowed:
        raise RuntimeError(f"Illegal sandbox runtime transition: {current} -> {target} ({reason})")
