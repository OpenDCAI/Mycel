"""Sandbox runtime implementations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sandbox.runtimes.base import PhysicalTerminalRuntime
from sandbox.runtimes.daytona import DaytonaSessionRuntime
from sandbox.runtimes.docker import DockerPtyRuntime
from sandbox.runtimes.e2b import E2BPtyRuntime
from sandbox.runtimes.local import LocalPersistentShellRuntime
from sandbox.runtimes.wrapped import RemoteWrappedRuntime

if TYPE_CHECKING:
    from sandbox.lease import SandboxLease
    from sandbox.provider import SandboxProvider
    from sandbox.terminal import AbstractTerminal


def create_runtime(
    provider: SandboxProvider,
    terminal: AbstractTerminal,
    lease: SandboxLease,
) -> PhysicalTerminalRuntime:
    capability = provider.get_capability()
    runtime_kind = str(getattr(capability, "runtime_kind", "remote"))
    if runtime_kind == "local":
        return LocalPersistentShellRuntime(terminal, lease)
    if runtime_kind == "docker_pty":
        return DockerPtyRuntime(terminal, lease, provider)
    if runtime_kind == "daytona_pty":
        return DaytonaSessionRuntime(terminal, lease, provider)
    if runtime_kind == "e2b_pty":
        return E2BPtyRuntime(terminal, lease, provider)
    return RemoteWrappedRuntime(terminal, lease, provider)


__all__ = [
    "PhysicalTerminalRuntime",
    "LocalPersistentShellRuntime",
    "RemoteWrappedRuntime",
    "DockerPtyRuntime",
    "DaytonaSessionRuntime",
    "E2BPtyRuntime",
    "create_runtime",
]
