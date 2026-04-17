from __future__ import annotations

from types import SimpleNamespace

from backend.web.services.thread_state_service import get_sandbox_info


def test_sandbox_info_does_not_expose_terminal_or_session_identity() -> None:
    terminal = SimpleNamespace(terminal_id="term-1", lease_id="lease-1")
    session = SimpleNamespace(session_id="session-1")
    lease = SimpleNamespace(
        observed_state="running",
        get_instance=lambda: SimpleNamespace(status="running", instance_id="instance-1"),
    )
    manager = SimpleNamespace(
        get_terminal=lambda _thread_id: terminal,
        session_manager=SimpleNamespace(get=lambda _thread_id, _terminal_id: session),
        get_lease=lambda _lease_id: lease,
        provider_capability=SimpleNamespace(runtime_kind="remote"),
    )
    agent = SimpleNamespace(_sandbox=SimpleNamespace(manager=manager))

    payload = get_sandbox_info(agent, "thread-1", "daytona")

    assert payload == {"type": "daytona", "status": "running"}
