from types import SimpleNamespace

import pytest

from sandbox.manager import SandboxManager


def _manager_for_provider(provider: SimpleNamespace) -> SandboxManager:
    manager = object.__new__(SandboxManager)
    manager.provider = provider
    manager.provider_capability = SimpleNamespace(inspect_visible=True)
    manager.terminal_store = SimpleNamespace(list_all=lambda: [])
    manager.session_manager = SimpleNamespace(list_all=lambda: [])
    manager.sandbox_runtime_store = SimpleNamespace(list_by_provider=lambda _provider_name: [])
    return manager


def test_provider_runtime_listing_propagates_provider_errors() -> None:
    def _raise_provider_error():
        raise RuntimeError("provider boom")

    manager = _manager_for_provider(SimpleNamespace(name="daytona", list_provider_runtimes=_raise_provider_error))

    with pytest.raises(RuntimeError, match="provider boom"):
        manager.list_sessions()


def test_provider_runtime_listing_rejects_non_list_provider_result() -> None:
    manager = _manager_for_provider(
        SimpleNamespace(name="daytona", list_provider_runtimes=lambda: (SimpleNamespace(session_id="runtime-1"),))
    )

    with pytest.raises(TypeError, match="daytona.list_provider_runtimes must return list"):
        manager.list_sessions()


def test_provider_runtime_listing_does_not_emit_legacy_runtime_id_field() -> None:
    manager = _manager_for_provider(
        SimpleNamespace(name="daytona", list_provider_runtimes=lambda: [SimpleNamespace(session_id="runtime-1", status="running")])
    )

    sessions = manager.list_sessions()

    assert len(sessions) == 1
    assert sessions[0]["source"] == "provider_orphan"
    assert "lea" "se_id" not in sessions[0]
