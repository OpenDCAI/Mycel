"""Monitor cleanup mutation contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SandboxCleanupRequest:
    sandbox_id: str
    sandbox_runtime_handle: str
    provider_name: str
    detach_thread_bindings: bool


@dataclass(frozen=True)
class ProviderOrphanRuntimeCleanupRequest:
    provider_name: str
    runtime_id: str


@dataclass(frozen=True)
class RuntimeMutationResult:
    destroy_result: Any
