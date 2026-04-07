import pytest
from pydantic import ValidationError

from storage.contracts import UserRow, UserType


def test_human_user_row_rejects_owner_user_id() -> None:
    with pytest.raises(ValidationError, match="human users must not carry owner_user_id"):
        UserRow(
            id="user-1",
            type=UserType.HUMAN,
            display_name="Owner",
            owner_user_id="owner-1",
            created_at=1.0,
        )


def test_human_user_row_rejects_agent_config_id() -> None:
    with pytest.raises(ValidationError, match="human users must not carry agent_config_id"):
        UserRow(
            id="user-1",
            type=UserType.HUMAN,
            display_name="Owner",
            agent_config_id="cfg-1",
            created_at=1.0,
        )


def test_agent_user_row_requires_owner_user_id() -> None:
    with pytest.raises(ValidationError, match="agent users require owner_user_id"):
        UserRow(
            id="user-1",
            type=UserType.AGENT,
            display_name="Toad",
            agent_config_id="cfg-1",
            created_at=1.0,
        )


def test_agent_user_row_requires_agent_config_id() -> None:
    with pytest.raises(ValidationError, match="agent users require agent_config_id"):
        UserRow(
            id="user-1",
            type=UserType.AGENT,
            display_name="Toad",
            owner_user_id="owner-1",
            created_at=1.0,
        )


def test_agent_user_row_accepts_owner_and_agent_config() -> None:
    row = UserRow(
        id="user-1",
        type=UserType.AGENT,
        display_name="Toad",
        owner_user_id="owner-1",
        agent_config_id="cfg-1",
        created_at=1.0,
    )

    assert row.type is UserType.AGENT
    assert row.owner_user_id == "owner-1"
    assert row.agent_config_id == "cfg-1"


def test_user_row_accepts_next_thread_seq() -> None:
    row = UserRow(
        id="user-1",
        type=UserType.AGENT,
        display_name="Toad",
        owner_user_id="owner-1",
        agent_config_id="cfg-1",
        next_thread_seq=7,
        created_at=1.0,
    )

    assert row.next_thread_seq == 7
