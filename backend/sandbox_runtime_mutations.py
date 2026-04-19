"""Shared sandbox runtime mutation helpers."""

from __future__ import annotations

from typing import Any

from backend.web.services import sandbox_service


def destroy_sandbox_runtime(
    *,
    lower_runtime_handle: str,
    provider_name: str,
    detach_thread_bindings: bool = False,
) -> dict[str, Any]:
    return sandbox_service.destroy_sandbox_runtime(
        lower_runtime_handle=lower_runtime_handle,
        provider_name=provider_name,
        detach_thread_bindings=detach_thread_bindings,
    )


def mutate_sandbox_runtime(
    *,
    runtime_id: str,
    action: str,
    provider_hint: str | None = None,
) -> dict[str, Any]:
    return sandbox_service.mutate_sandbox_runtime(
        runtime_id=runtime_id,
        action=action,
        provider_hint=provider_hint,
    )
