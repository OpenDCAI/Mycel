"""Provider runtime inventory read port for Monitor."""

from __future__ import annotations

from typing import Any

from backend.sandboxes.inventory import list_provider_orphan_runtimes


def load_provider_orphan_runtime_rows() -> list[dict[str, Any]]:
    return list_provider_orphan_runtimes()
