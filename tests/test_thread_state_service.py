from types import SimpleNamespace
from unittest.mock import MagicMock

from backend.web.services.thread_state_service import get_sandbox_info


def test_get_sandbox_info_converges_local_lease_without_bound_instance():
    instance = SimpleNamespace(instance_id="local-123", status="running")
    lease = SimpleNamespace(
        get_instance=MagicMock(return_value=None),
        ensure_active_instance=MagicMock(return_value=instance),
        observed_state="detached",
    )
    terminal = SimpleNamespace(terminal_id="term-123", lease_id="lease-123")
    provider = SimpleNamespace(name="local")
    provider_capability = SimpleNamespace(runtime_kind="local")
    mgr = SimpleNamespace(
        provider=provider,
        provider_capability=provider_capability,
        get_terminal=MagicMock(return_value=terminal),
        get_lease=MagicMock(return_value=lease),
        session_manager=SimpleNamespace(get=MagicMock(return_value=None)),
    )
    agent = SimpleNamespace(_sandbox=SimpleNamespace(manager=mgr))

    result = get_sandbox_info(agent, "thread-123", "local")

    assert result["type"] == "local"
    assert result["status"] == "running"
    assert result["session_id"] == "local-123"
    lease.ensure_active_instance.assert_called_once_with(provider)
