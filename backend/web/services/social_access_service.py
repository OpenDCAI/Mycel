"""Social access rules for entity discovery and group chat creation."""

from __future__ import annotations

from typing import Any

ACTIVE_CHAT_RELATIONSHIP_STATES = {"visit", "hire"}


def is_active_contact_edge(row: Any) -> bool:
    return (
        row is not None
        and getattr(row, "kind", None) == "normal"
        and getattr(row, "state", None) == "active"
        and not bool(getattr(row, "blocked", False))
    )


def active_contact_target_ids(contact_repo: Any, owner_user_id: str) -> set[str]:
    if contact_repo is None:
        raise RuntimeError("contact_repo is required for social access checks")
    return {row.target_user_id for row in contact_repo.list_for_user(owner_user_id) if is_active_contact_edge(row)}


def has_active_contact(contact_repo: Any, owner_user_id: str, target_user_id: str) -> bool:
    if contact_repo is None:
        raise RuntimeError("contact_repo is required for social access checks")
    return is_active_contact_edge(contact_repo.get(owner_user_id, target_user_id))


def can_chat_with(*, is_owned: bool, relationship_state: str, has_contact: bool) -> bool:
    return is_owned or has_contact or relationship_state in ACTIVE_CHAT_RELATIONSHIP_STATES


def can_chat_with_owner_scope(
    *,
    is_owned: bool,
    relationship_state: str,
    has_contact: bool,
    owner_relationship_state: str | None,
    owner_has_contact: bool,
) -> bool:
    return can_chat_with(is_owned=is_owned, relationship_state=relationship_state, has_contact=has_contact) or (
        not is_owned and (owner_has_contact or owner_relationship_state in ACTIVE_CHAT_RELATIONSHIP_STATES)
    )
