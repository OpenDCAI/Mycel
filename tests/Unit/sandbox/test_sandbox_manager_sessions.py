from types import SimpleNamespace

import pytest

from sandbox.manager import SandboxManager


def _manager_for_provider(provider: SimpleNamespace) -> SandboxManager:
    manager = object.__new__(SandboxManager)
    manager.provider = provider
    manager.provider_capability = SimpleNamespace(inspect_visible=True)
    manager.terminal_store = SimpleNamespace(list_all=lambda: [])
    manager.session_manager = SimpleNamespace(list_all=lambda: [])
    manager.lease_store = SimpleNamespace(list_by_provider=lambda _provider_name: [])
    return manager


def test_list_sessions_propagates_provider_runtime_list_errors() -> None:
    def _raise_provider_error():
        raise RuntimeError("provider boom")

    manager = _manager_for_provider(SimpleNamespace(name="daytona", list_provider_runtimes=_raise_provider_error))

    with pytest.raises(RuntimeError, match="provider boom"):
        manager.list_sessions()


def test_list_sessions_rejects_non_list_provider_runtime_result() -> None:
    manager = _manager_for_provider(
        SimpleNamespace(name="daytona", list_provider_runtimes=lambda: (SimpleNamespace(session_id="runtime-1"),))
    )

    with pytest.raises(TypeError, match="daytona.list_provider_runtimes must return list"):
        manager.list_sessions()
