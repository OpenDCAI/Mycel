from __future__ import annotations

from core.identity import agent_registry


def test_get_or_create_agent_id_derives_stable_user_id_contract():
    agent_id = agent_registry.get_or_create_agent_id(
        user_id="agent-user-1",
        thread_id="thread-1",
        sandbox_type="local",
    )

    assert agent_id == agent_registry.get_or_create_agent_id(
        user_id="agent-user-1",
        thread_id="thread-1",
        sandbox_type="local",
    )
    assert agent_id != agent_registry.get_or_create_agent_id(
        user_id="agent-user-2",
        thread_id="thread-1",
        sandbox_type="local",
    )


def test_get_or_create_agent_id_does_not_write_process_local_registry(tmp_path):
    registry_file = tmp_path / ".leon" / "agent_instances.json"

    first = agent_registry.get_or_create_agent_id(
        user_id="agent-user-1",
        thread_id="thread-1",
        sandbox_type="local",
    )
    second = agent_registry.get_or_create_agent_id(
        user_id="agent-user-1",
        thread_id="thread-1",
        sandbox_type="local",
    )

    assert first == second
    assert not registry_file.exists()
    assert not registry_file.parent.exists()
