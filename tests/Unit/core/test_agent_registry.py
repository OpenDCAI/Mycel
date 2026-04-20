from __future__ import annotations

from core.identity import agent_registry


def test_get_or_create_agent_id_persists_user_id_contract(monkeypatch):
    saved: dict[str, object] = {}

    monkeypatch.setattr(agent_registry, "_load", lambda: {})
    monkeypatch.setattr(agent_registry, "_save", lambda data: saved.update(data))
    monkeypatch.setattr(agent_registry.uuid, "uuid4", lambda: type("U", (), {"hex": "abcdef1234567890"})())

    agent_id = agent_registry.get_or_create_agent_id(
        user_id="agent-user-1",
        thread_id="thread-1",
        sandbox_type="local",
    )

    assert agent_id == "abcdef12"
    assert saved[agent_id]["user_id"] == "agent-user-1"
    assert "member" not in saved[agent_id]
