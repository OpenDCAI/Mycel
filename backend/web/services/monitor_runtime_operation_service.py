"""Runtime mutation executor for Monitor operations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.web.services import sandbox_service


@dataclass(frozen=True)
class SandboxCleanupRequest:
    lower_runtime_handle: str
    provider_name: str
    detach_thread_bindings: bool


@dataclass(frozen=True)
class ProviderOrphanRuntimeCleanupRequest:
    provider_name: str
    runtime_id: str


def execute_sandbox_cleanup(request: SandboxCleanupRequest) -> Any:
    return sandbox_service.destroy_sandbox_runtime(
        lower_runtime_handle=request.lower_runtime_handle,
        provider_name=request.provider_name,
        detach_thread_bindings=request.detach_thread_bindings,
    )


def execute_provider_orphan_runtime_cleanup(request: ProviderOrphanRuntimeCleanupRequest) -> Any:
    return sandbox_service.mutate_sandbox_runtime(
        runtime_id=request.runtime_id,
        action="destroy",
        provider_hint=request.provider_name,
    )
