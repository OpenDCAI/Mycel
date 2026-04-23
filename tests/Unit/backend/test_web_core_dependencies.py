from types import SimpleNamespace

import pytest

from backend.web.core import dependencies as web_dependencies


@pytest.mark.asyncio
async def test_get_thread_agent_passes_borrowed_messaging_service_to_agent_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    messaging_service = object()
    app = SimpleNamespace(
        state=SimpleNamespace(
            threads_runtime_state=SimpleNamespace(messaging_service=messaging_service),
        )
    )

    async def _fake_get_or_create_agent(_app, _sandbox_type: str, *, thread_id: str, messaging_service=None):
        captured["thread_id"] = thread_id
        captured["messaging_service"] = messaging_service
        return SimpleNamespace(_sandbox=SimpleNamespace(name="local"))

    monkeypatch.setattr(web_dependencies, "resolve_thread_sandbox", lambda _app, _thread_id: "local")
    monkeypatch.setattr(web_dependencies, "get_or_create_agent", _fake_get_or_create_agent)

    agent = await web_dependencies.get_thread_agent(app=app, thread_id="thread-1")

    assert agent._sandbox.name == "local"
    assert captured == {
        "thread_id": "thread-1",
        "messaging_service": messaging_service,
    }
