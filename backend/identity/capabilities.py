from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from fastapi import HTTPException

from storage.contracts import UserType


class Capability(StrEnum):
    CREATE_EXTERNAL_USER = "create_external_user"
    CREATE_MANAGED_AGENT = "create_managed_agent"
    MANAGE_INVITE_CODES = "manage_invite_codes"
    USE_SANDBOX = "use_sandbox"
    INSPECT_RESOURCES = "inspect_resources"


_COMMUNICATION_CAPABILITIES = frozenset[Capability]()
_GUEST_OWNER_CAPABILITIES = frozenset({Capability.CREATE_EXTERNAL_USER})
_OWNER_CAPABILITIES = frozenset(Capability)
_CAPABILITIES_BY_USER_TYPE = {
    UserType.AGENT: _COMMUNICATION_CAPABILITIES,
    UserType.EXTERNAL: _COMMUNICATION_CAPABILITIES,
}


@dataclass(frozen=True)
class UserCapabilities:
    user_id: str
    values: frozenset[Capability]

    def has(self, capability: Capability) -> bool:
        return capability in self.values


def resolve_user_capabilities(user: Any) -> UserCapabilities:
    raw_user_type = getattr(user, "type", None)
    user_type: UserType | None
    if isinstance(raw_user_type, UserType):
        user_type = raw_user_type
    elif isinstance(raw_user_type, str):
        try:
            user_type = UserType(raw_user_type)
        except ValueError as exc:
            raise HTTPException(403, "Unknown user capability profile") from exc
    else:
        user_type = None
    user_id = str(getattr(user, "id", ""))
    if user_type is None:
        raise HTTPException(403, "Unknown user capability profile")
    if user_type is UserType.HUMAN:
        values = _OWNER_CAPABILITIES
        if bool(getattr(user, "is_guest", False)):
            values = _GUEST_OWNER_CAPABILITIES
    else:
        values = _CAPABILITIES_BY_USER_TYPE[user_type]
    return UserCapabilities(user_id=user_id, values=values)


def require_user_capability(user: Any, capability: Capability) -> None:
    capabilities = resolve_user_capabilities(user)
    if not capabilities.has(capability):
        raise HTTPException(403, f"Capability required: {capability.value}")
