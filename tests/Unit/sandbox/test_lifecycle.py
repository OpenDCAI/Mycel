import pytest

from sandbox.lifecycle import (
    ChatSessionState,
    LeaseInstanceState,
    assert_chat_session_transition,
    assert_lease_instance_transition,
    parse_chat_session_state,
    parse_lease_instance_state,
)


def test_parse_chat_session_state_rejects_invalid():
    with pytest.raises(RuntimeError, match="Invalid ChatSession state"):
        parse_chat_session_state("weird")


def test_parse_lease_instance_state_maps_deleted_like_values():
    assert parse_lease_instance_state("deleted") == LeaseInstanceState.DETACHED
    assert parse_lease_instance_state("dead") == LeaseInstanceState.DETACHED
    assert parse_lease_instance_state("stopped") == LeaseInstanceState.DETACHED


def test_chat_session_transition_rejects_closed_to_active():
    with pytest.raises(RuntimeError, match="Illegal chat session transition"):
        assert_chat_session_transition(
            ChatSessionState.CLOSED,
            ChatSessionState.ACTIVE,
            reason="test",
        )


def test_lease_transition_rejects_detached_to_paused():
    with pytest.raises(RuntimeError, match="Illegal lease transition"):
        assert_lease_instance_transition(
            LeaseInstanceState.DETACHED,
            LeaseInstanceState.PAUSED,
            reason="test",
        )
