import pytest

from sandbox.lifecycle import (
    ChatSessionState,
    SandboxRuntimeInstanceState,
    assert_chat_session_transition,
    assert_sandbox_runtime_instance_transition,
    parse_chat_session_state,
    parse_sandbox_runtime_instance_state,
)


def test_parse_chat_session_state_rejects_invalid():
    with pytest.raises(RuntimeError, match="Invalid ChatSession state"):
        parse_chat_session_state("weird")


def test_parse_sandbox_runtime_instance_state_rejects_invalid():
    with pytest.raises(RuntimeError, match="Invalid SandboxRuntimeInstance state"):
        parse_sandbox_runtime_instance_state("weird")


def test_parse_sandbox_runtime_instance_state_maps_deleted_like_values():
    assert parse_sandbox_runtime_instance_state("deleted") == SandboxRuntimeInstanceState.DETACHED
    assert parse_sandbox_runtime_instance_state("dead") == SandboxRuntimeInstanceState.DETACHED
    assert parse_sandbox_runtime_instance_state("stopped") == SandboxRuntimeInstanceState.DETACHED


def test_chat_session_transition_rejects_closed_to_active():
    with pytest.raises(RuntimeError, match="Illegal chat session transition"):
        assert_chat_session_transition(
            ChatSessionState.CLOSED,
            ChatSessionState.ACTIVE,
            reason="test",
        )


def test_sandbox_runtime_transition_rejects_detached_to_paused():
    with pytest.raises(RuntimeError, match="Illegal sandbox runtime transition"):
        assert_sandbox_runtime_instance_transition(
            SandboxRuntimeInstanceState.DETACHED,
            SandboxRuntimeInstanceState.PAUSED,
            reason="test",
        )
