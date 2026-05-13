from __future__ import annotations

from types import SimpleNamespace

from messaging.social_access import can_group_chat_with_participant


def test_group_chat_participant_allowed_by_active_contact() -> None:
    contact_repo = SimpleNamespace(
        get=lambda viewer_id, target_id: (
            SimpleNamespace(state="active", kind="normal", blocked=False) if (viewer_id, target_id) == ("viewer-1", "human-2") else None
        )
    )
    relationship_service = SimpleNamespace(get_state=lambda _viewer_id, _target_id: "none")

    allowed = can_group_chat_with_participant(
        viewer_user_id="viewer-1",
        participant_user_id="human-2",
        participant_user=SimpleNamespace(id="human-2", owner_user_id=None),
        contact_repo=contact_repo,
        relationship_service=relationship_service,
    )

    assert allowed is True


def test_group_chat_participant_allowed_by_owner_relationship_scope() -> None:
    contact_repo = SimpleNamespace(get=lambda _viewer_id, _target_id: None)
    relationship_service = SimpleNamespace(
        get_state=lambda viewer_id, target_id: "visit" if (viewer_id, target_id) == ("viewer-1", "owner-2") else "none"
    )

    allowed = can_group_chat_with_participant(
        viewer_user_id="viewer-1",
        participant_user_id="agent-2",
        participant_user=SimpleNamespace(id="agent-2", owner_user_id="owner-2"),
        contact_repo=contact_repo,
        relationship_service=relationship_service,
    )

    assert allowed is True


def test_group_chat_participant_denied_without_contact_or_relationship() -> None:
    contact_repo = SimpleNamespace(get=lambda _viewer_id, _target_id: None)
    relationship_service = SimpleNamespace(get_state=lambda _viewer_id, _target_id: "none")

    allowed = can_group_chat_with_participant(
        viewer_user_id="viewer-1",
        participant_user_id="human-2",
        participant_user=SimpleNamespace(id="human-2", owner_user_id=None),
        contact_repo=contact_repo,
        relationship_service=relationship_service,
    )

    assert allowed is False
