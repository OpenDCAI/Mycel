"""Shared sandbox recipe catalog helpers."""

from __future__ import annotations

from backend.sandboxes.inventory import available_sandbox_types
from sandbox.recipes import list_builtin_recipes


def list_default_recipes() -> list[dict[str, object]]:
    return list_builtin_recipes(available_sandbox_types())
