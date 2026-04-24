from __future__ import annotations

from typing import Any

from backend.sandboxes.resources.io import (
    browse_sandbox as run_browse_sandbox,
)
from backend.sandboxes.resources.io import (
    read_sandbox as run_read_sandbox,
)
from backend.sandboxes.resources.io import (
    refresh_resource_snapshots as run_refresh_resource_snapshots,
)


def refresh_resource_snapshots() -> dict[str, Any]:
    return run_refresh_resource_snapshots()


def browse_sandbox(sandbox_id: str, path: str) -> dict[str, Any]:
    return run_browse_sandbox(sandbox_id, path)


def read_sandbox(sandbox_id: str, path: str) -> dict[str, Any]:
    return run_read_sandbox(sandbox_id, path)
