from __future__ import annotations

import inspect

from sandbox.provider import SandboxProvider
from sandbox.providers.agentbay import AgentBayProvider
from sandbox.providers.daytona import DaytonaProvider
from sandbox.providers.docker import DockerProvider
from sandbox.providers.e2b import E2BProvider
from sandbox.providers.local import LocalSessionProvider


def test_create_runtime_interface_uses_sandbox_runtime_parameter_name() -> None:
    parameter_names = list(inspect.signature(SandboxProvider.create_runtime).parameters)

    assert parameter_names == ["self", "terminal", "sandbox_runtime"]


def test_concrete_providers_use_sandbox_runtime_parameter_name() -> None:
    for provider_cls in [LocalSessionProvider, DockerProvider, E2BProvider, DaytonaProvider, AgentBayProvider]:
        parameter_names = list(inspect.signature(provider_cls.create_runtime).parameters)
        assert parameter_names == ["self", "terminal", "sandbox_runtime"]
