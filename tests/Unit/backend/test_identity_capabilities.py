from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.identity.capabilities import Capability, require_user_capability, resolve_user_capabilities
from storage.contracts import UserType


def _user(user_id: str, user_type: UserType | str):
    return SimpleNamespace(id=user_id, type=user_type)


def _owner(user_id: str, owner_profile: str | None = None):
    return SimpleNamespace(id=user_id, type=UserType.HUMAN, owner_profile=owner_profile)


def test_human_owner_has_admin_capabilities() -> None:
    capabilities = resolve_user_capabilities(_user("owner-1", UserType.HUMAN))

    assert capabilities.user_id == "owner-1"
    assert capabilities.has(Capability.CREATE_EXTERNAL_USER)
    assert capabilities.has(Capability.MANAGE_INVITE_CODES)
    assert capabilities.has(Capability.USE_SANDBOX)


def test_guest_owner_has_communication_profile_only() -> None:
    capabilities = resolve_user_capabilities(_owner("guest-1", "guest"))

    assert capabilities.has(Capability.CREATE_EXTERNAL_USER)
    assert not capabilities.has(Capability.CREATE_MANAGED_AGENT)
    assert not capabilities.has(Capability.MANAGE_INVITE_CODES)
    assert not capabilities.has(Capability.USE_SANDBOX)


def test_external_user_has_communication_profile_only() -> None:
    capabilities = resolve_user_capabilities(_user("external-1", UserType.EXTERNAL))

    assert not capabilities.has(Capability.CREATE_EXTERNAL_USER)
    assert not capabilities.has(Capability.MANAGE_INVITE_CODES)
    assert not capabilities.has(Capability.USE_SANDBOX)


def test_require_user_capability_fails_loud_for_external_user() -> None:
    with pytest.raises(HTTPException) as exc_info:
        require_user_capability(_user("external-1", "external"), Capability.CREATE_EXTERNAL_USER)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Capability required: create_external_user"


def test_unknown_user_type_fails_loud() -> None:
    with pytest.raises(HTTPException) as exc_info:
        resolve_user_capabilities(_user("odd-1", "odd"))

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Unknown user capability profile"
