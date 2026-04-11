from storage.utils import generate_agent_config_id, generate_agent_user_id


def test_generate_agent_user_id_uses_agent_user_prefix() -> None:
    agent_user_id = generate_agent_user_id()

    assert agent_user_id.startswith("m_")
    assert len(agent_user_id) == 14


def test_generate_agent_config_id_uses_config_prefix() -> None:
    agent_config_id = generate_agent_config_id()

    assert agent_config_id.startswith("cfg_")
    assert len(agent_config_id) == 16
