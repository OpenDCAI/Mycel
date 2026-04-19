"""Shared sandbox inventory helpers."""

from __future__ import annotations

from typing import Any

from backend.web.services import sandbox_service


def available_sandbox_types() -> list[dict[str, Any]]:
    return sandbox_service.available_sandbox_types()


def list_provider_orphan_runtimes() -> list[dict[str, Any]]:
    return sandbox_service.list_provider_orphan_runtimes()
