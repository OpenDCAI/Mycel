from __future__ import annotations

from typing import Any

from backend.sandboxes.inventory import available_sandbox_types as load_available_sandbox_types


def available_sandbox_types() -> list[dict[str, Any]]:
    return load_available_sandbox_types()
