"""Monitor sandbox mutation port."""

from __future__ import annotations

from typing import Any

from backend.monitor.mutations.contracts import (
    ProviderOrphanRuntimeCleanupRequest,
    RuntimeMutationResult,
    SandboxCleanupRequest,
)
from backend.sandboxes.runtime.mutations import destroy_sandbox_runtime, mutate_sandbox_runtime


def _public_destroy_result(result: Any) -> Any:
    if not isinstance(result, dict):
        return result
    return {key: value for key, value in result.items() if key not in {"lease_id", "lower_runtime_handle"}}


def cleanup_sandbox(request: SandboxCleanupRequest) -> RuntimeMutationResult:
    result = destroy_sandbox_runtime(
        lower_runtime_handle=request.lower_runtime_handle,
        provider_name=request.provider_name,
        detach_thread_bindings=request.detach_thread_bindings,
    )
    return RuntimeMutationResult(destroy_result=_public_destroy_result(result))


def cleanup_provider_orphan_runtime(request: ProviderOrphanRuntimeCleanupRequest) -> RuntimeMutationResult:
    result = mutate_sandbox_runtime(
        runtime_id=request.runtime_id,
        action="destroy",
        provider_hint=request.provider_name,
    )
    return RuntimeMutationResult(destroy_result=_public_destroy_result(result))
