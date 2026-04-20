"""Sandbox provider inventory port for Monitor config projection."""

from __future__ import annotations

from typing import Any

from backend.sandbox_inventory import available_sandbox_types as load_available_sandbox_types


def available_sandbox_types() -> list[dict[str, Any]]:
    return load_available_sandbox_types()
