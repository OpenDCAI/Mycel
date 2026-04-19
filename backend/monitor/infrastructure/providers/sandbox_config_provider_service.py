"""Sandbox provider inventory port for Monitor config projection."""

from __future__ import annotations

from typing import Any

from backend.web.services import sandbox_service


def available_sandbox_types() -> list[dict[str, Any]]:
    return sandbox_service.available_sandbox_types()
