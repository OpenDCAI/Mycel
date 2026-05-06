from __future__ import annotations

import pytest

from storage.contracts import OwnerProfile, UserRow, UserType


def test_external_user_row_requires_creator_and_no_agent_config() -> None:
    row = UserRow(
        id="external-user-1",
        type=UserType.EXTERNAL,
        display_name="Codex External",
        agent_config_id=None,
        created_by_user_id="owner-1",
        created_at=1.0,
    )

    assert row.type is UserType.EXTERNAL
    assert row.owner_user_id is None
    assert row.agent_config_id is None
    assert row.created_by_user_id == "owner-1"


def test_external_user_row_rejects_missing_created_by_user_id() -> None:
    with pytest.raises(ValueError, match="external users require created_by_user_id"):
        UserRow(
            id="external-user-1",
            type=UserType.EXTERNAL,
            display_name="Codex External",
            created_at=1.0,
        )


def test_external_user_row_rejects_owner_user_id() -> None:
    with pytest.raises(ValueError, match="external users must not carry owner_user_id"):
        UserRow(
            id="external-user-1",
            type=UserType.EXTERNAL,
            display_name="Codex External",
            owner_user_id="owner-1",
            created_by_user_id="creator-1",
            created_at=1.0,
        )


def test_external_user_row_rejects_agent_config_id() -> None:
    with pytest.raises(ValueError, match="external users must not carry agent_config_id"):
        UserRow(
            id="external-user-1",
            type=UserType.EXTERNAL,
            display_name="Codex External",
            created_by_user_id="owner-1",
            agent_config_id="cfg-1",
            created_at=1.0,
        )


def test_human_user_row_can_carry_guest_owner_profile() -> None:
    row = UserRow(
        id="guest-owner-1",
        type=UserType.HUMAN,
        display_name="Guest",
        owner_profile=OwnerProfile.GUEST,
        created_at=1.0,
    )

    assert row.owner_profile is OwnerProfile.GUEST


def test_agent_and_external_rows_reject_owner_profile() -> None:
    with pytest.raises(ValueError, match="external users must not carry owner_profile"):
        UserRow(
            id="external-user-1",
            type=UserType.EXTERNAL,
            display_name="Codex External",
            created_by_user_id="owner-1",
            owner_profile=OwnerProfile.GUEST,
            created_at=1.0,
        )

    with pytest.raises(ValueError, match="agent users must not carry owner_profile"):
        UserRow(
            id="agent-1",
            type=UserType.AGENT,
            display_name="Toad",
            owner_user_id="owner-1",
            agent_config_id="cfg-1",
            owner_profile=OwnerProfile.GUEST,
            created_at=1.0,
        )
