from __future__ import annotations

from types import SimpleNamespace

from messaging.user_ownership import access_scope_targets, is_owned_by_viewer


def test_is_owned_by_viewer_accepts_self() -> None:
    user = SimpleNamespace(id="viewer-1", owner_user_id=None)

    assert is_owned_by_viewer("viewer-1", user) is True


def test_is_owned_by_viewer_accepts_owned_agent_user() -> None:
    user = SimpleNamespace(id="agent-user-1", owner_user_id="viewer-1")

    assert is_owned_by_viewer("viewer-1", user) is True


def test_is_owned_by_viewer_rejects_stranger() -> None:
    user = SimpleNamespace(id="agent-user-1", owner_user_id="someone-else")

    assert is_owned_by_viewer("viewer-1", user) is False


def test_is_owned_by_viewer_rejects_missing_candidate() -> None:
    assert is_owned_by_viewer("viewer-1", None) is False


def test_access_scope_targets_expands_owned_user_scope() -> None:
    user = SimpleNamespace(id="agent-user-1", owner_user_id="viewer-1")

    assert access_scope_targets(user, user_id="agent-user-1") == ["agent-user-1", "viewer-1"]


def test_access_scope_targets_uses_user_id_without_owner_scope() -> None:
    user = SimpleNamespace(id="human-user-2", owner_user_id=None)

    assert access_scope_targets(user, user_id="human-user-2") == ["human-user-2"]
