from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.web.services.streaming_service import prime_sandbox


@pytest.mark.asyncio
async def test_prime_sandbox_uses_capability_session_not_terminal_lookup() -> None:
    resume_calls: list[str] = []
    lease = SimpleNamespace(refresh_instance_status=lambda _provider: "running")
    capability = SimpleNamespace(_session=SimpleNamespace(lease=lease))
    manager = SimpleNamespace(
        enforce_idle_timeouts=lambda: None,
        get_sandbox=lambda thread_id: capability,
        get_terminal=lambda _thread_id: (_ for _ in ()).throw(AssertionError("prime_sandbox should not read terminal directly")),
        provider=object(),
        provider_capability=SimpleNamespace(can_resume=True),
    )
    agent = SimpleNamespace(
        _sandbox=SimpleNamespace(
            manager=manager,
            resume_thread=lambda thread_id: resume_calls.append(thread_id) or True,
        )
    )

    await prime_sandbox(agent, "thread-1")

    assert resume_calls == []


@pytest.mark.asyncio
async def test_prime_sandbox_resumes_paused_lease_from_capability_session() -> None:
    resume_calls: list[str] = []
    lease = SimpleNamespace(refresh_instance_status=lambda _provider: "paused")
    capability = SimpleNamespace(_session=SimpleNamespace(lease=lease))
    manager = SimpleNamespace(
        enforce_idle_timeouts=lambda: None,
        get_sandbox=lambda thread_id: capability,
        provider=object(),
        provider_capability=SimpleNamespace(can_resume=True),
    )
    agent = SimpleNamespace(
        _sandbox=SimpleNamespace(
            manager=manager,
            resume_thread=lambda thread_id: resume_calls.append(thread_id) or True,
        )
    )

    await prime_sandbox(agent, "thread-1")

    assert resume_calls == ["thread-1"]
