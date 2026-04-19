"""Shared resource refresh and sandbox file IO helpers."""

from __future__ import annotations

from typing import Any

from backend.web.services import resource_service


def refresh_resource_snapshots() -> dict[str, Any]:
    return resource_service.refresh_resource_snapshots()


def browse_sandbox(sandbox_id: str, path: str) -> dict[str, Any]:
    return resource_service.browse_sandbox(sandbox_id, path)


def read_sandbox(sandbox_id: str, path: str) -> dict[str, Any]:
    return resource_service.read_sandbox(sandbox_id, path)
