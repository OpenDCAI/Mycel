from __future__ import annotations

import os
from enum import StrEnum


class RuntimeProfile(StrEnum):
    FULL = "full"
    COMMUNICATION = "communication"


def resolve_runtime_profile(raw: str | None = None) -> RuntimeProfile:
    value = (raw if raw is not None else os.getenv("MYCEL_RUNTIME_PROFILE") or RuntimeProfile.FULL.value).strip().lower()
    try:
        return RuntimeProfile(value)
    except ValueError as exc:
        allowed = ", ".join(profile.value for profile in RuntimeProfile)
        raise RuntimeError(f"MYCEL_RUNTIME_PROFILE must be one of: {allowed}") from exc
