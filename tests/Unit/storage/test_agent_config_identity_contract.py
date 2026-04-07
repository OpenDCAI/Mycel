import pytest
from pydantic import ValidationError

from storage.contracts import AgentConfigRow, AgentRuleRow, AgentSkillRow, AgentSubAgentRow


def test_agent_config_row_rejects_blank_agent_user_id() -> None:
    with pytest.raises(ValidationError, match="agent_config.agent_user_id must not be blank"):
        AgentConfigRow(
            id="cfg-1",
            agent_user_id="   ",
            name="Toad",
            created_at=1,
        )


def test_agent_config_row_rejects_blank_id() -> None:
    with pytest.raises(ValidationError, match="agent_config.id must not be blank"):
        AgentConfigRow(
            id=" ",
            agent_user_id="agent-user-1",
            name="Toad",
            created_at=1,
        )


def test_agent_config_row_rejects_blank_name() -> None:
    with pytest.raises(ValidationError, match="agent_config.name must not be blank"):
        AgentConfigRow(
            id="cfg-1",
            agent_user_id="agent-user-1",
            name=" ",
            created_at=1,
        )


def test_agent_config_row_uses_independent_runtime_and_mcp_defaults() -> None:
    first = AgentConfigRow(
        id="cfg-1",
        agent_user_id="agent-user-1",
        name="Toad",
        created_at=1,
    )
    second = AgentConfigRow(
        id="cfg-2",
        agent_user_id="agent-user-2",
        name="Morel",
        created_at=2,
    )

    first.runtime["sandbox"] = {"enabled": True}
    first.mcp["filesystem"] = {"disabled": False}

    assert second.runtime == {}
    assert second.mcp == {}


def test_agent_rule_row_rejects_blank_agent_config_id() -> None:
    with pytest.raises(ValidationError, match="agent_rule.agent_config_id must not be blank"):
        AgentRuleRow(
            id="rule-1",
            agent_config_id=" ",
            filename="default.md",
            content="Be careful.",
        )


def test_agent_rule_row_rejects_blank_id() -> None:
    with pytest.raises(ValidationError, match="agent_rule.id must not be blank"):
        AgentRuleRow(
            id=" ",
            agent_config_id="cfg-1",
            filename="default.md",
            content="Be careful.",
        )


def test_agent_skill_row_defaults_meta_to_independent_dict() -> None:
    first = AgentSkillRow(
        id="skill-1",
        agent_config_id="cfg-1",
        name="Search",
        content="search skill",
    )
    second = AgentSkillRow(
        id="skill-2",
        agent_config_id="cfg-1",
        name="Write",
        content="write skill",
    )

    first.meta["enabled"] = True

    assert second.meta == {}


def test_agent_skill_row_rejects_blank_id() -> None:
    with pytest.raises(ValidationError, match="agent_skill.id must not be blank"):
        AgentSkillRow(
            id=" ",
            agent_config_id="cfg-1",
            name="Search",
            content="search skill",
        )


def test_agent_sub_agent_row_rejects_blank_agent_config_id() -> None:
    with pytest.raises(ValidationError, match="agent_sub_agent.agent_config_id must not be blank"):
        AgentSubAgentRow(
            id="sub-1",
            agent_config_id=" ",
            name="Scout",
        )


def test_agent_sub_agent_row_rejects_blank_id() -> None:
    with pytest.raises(ValidationError, match="agent_sub_agent.id must not be blank"):
        AgentSubAgentRow(
            id=" ",
            agent_config_id="cfg-1",
            name="Scout",
        )
