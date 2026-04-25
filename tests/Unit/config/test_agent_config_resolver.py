import inspect

import pytest

from config.agent_config_resolver import resolve_agent_config
from config.agent_config_types import (
    AgentConfig,
    AgentRule,
    AgentSkill,
    AgentSubAgent,
    McpServerConfig,
)


def _skill(name: str = "github", *, enabled: bool = True, content: str | None = None) -> AgentSkill:
    return AgentSkill(
        name=name,
        description="GitHub guidance",
        version="1.0.0",
        enabled=enabled,
        content=content
        or """---
name: github
description: Use gh.
---

# GitHub

Use gh with explicit repositories.
""",
        files={"references/query.md": "Prefer precise queries."},
        source={"marketplace_item_id": "skill-github", "source_version": "1.0.0"},
    )


def _config(**overrides: object) -> AgentConfig:
    data = {
        "id": "cfg-1",
        "owner_user_id": "owner-1",
        "agent_user_id": "agent-1",
        "name": "Researcher",
        "description": "Research agent",
        "model": "gpt-test",
        "tools": ["read", "shell"],
        "system_prompt": "Base prompt",
        "runtime_settings": {"shell": {"enabled": False}},
        "compact": {"enabled": True},
        "meta": {"source": "unit"},
    }
    data.update(overrides)
    return AgentConfig(**data)


def test_resolved_config_contains_only_enabled_children():
    config = _config(
        skills=[_skill("github"), _skill("disabled", enabled=False)],
        rules=[
            AgentRule(name="Cite", content="Always cite sources.", enabled=True),
            AgentRule(name="Skip", content="Skip me.", enabled=False),
        ],
        sub_agents=[
            AgentSubAgent(name="Planner", system_prompt="Plan", enabled=True),
            AgentSubAgent(name="Muted", system_prompt="Muted", enabled=False),
        ],
        mcp_servers=[
            McpServerConfig(name="filesystem", transport="stdio", command="fs", enabled=True),
            McpServerConfig(name="off", transport="stdio", command="off", enabled=False),
        ],
    )

    resolved = resolve_agent_config(config)

    assert resolved.id == "cfg-1"
    assert resolved.name == "Researcher"
    assert [skill.name for skill in resolved.skills] == ["github"]
    assert resolved.skills[0].files == {"references/query.md": "Prefer precise queries."}
    assert [rule.name for rule in resolved.rules] == ["Cite"]
    assert [agent.name for agent in resolved.sub_agents] == ["Planner"]
    assert [server.name for server in resolved.mcp_servers] == ["filesystem"]


def test_agent_skill_rejects_blank_content():
    with pytest.raises(ValueError) as excinfo:
        AgentSkill(name="broken", content="")

    assert "agent_skill.content must not be blank" in str(excinfo.value)


def test_agent_named_children_reject_blank_names():
    with pytest.raises(ValueError) as rule_excinfo:
        AgentRule(name=" ", content="body")
    with pytest.raises(ValueError) as sub_agent_excinfo:
        AgentSubAgent(name=" ")
    with pytest.raises(ValueError) as mcp_excinfo:
        McpServerConfig(name=" ")

    assert "agent_rule.name must not be blank" in str(rule_excinfo.value)
    assert "agent_sub_agent.name must not be blank" in str(sub_agent_excinfo.value)
    assert "mcp_server.name must not be blank" in str(mcp_excinfo.value)


def test_agent_config_rejects_blank_identity_fields():
    for field_name in ("id", "owner_user_id", "agent_user_id", "name"):
        data = {
            "id": "cfg-1",
            "owner_user_id": "owner-1",
            "agent_user_id": "agent-1",
            "name": "Researcher",
        }
        data[field_name] = " "

        with pytest.raises(ValueError) as excinfo:
            AgentConfig(**data)

        assert f"agent_config.{field_name} must not be blank" in str(excinfo.value)


def test_resolver_rejects_skill_without_frontmatter():
    config = _config(skills=[AgentSkill.model_construct(name="broken", content="# Missing")])

    with pytest.raises(ValueError) as excinfo:
        resolve_agent_config(config)

    assert "missing SKILL.md frontmatter" in str(excinfo.value)


def test_resolver_rejects_skill_frontmatter_without_name():
    config = _config(
        skills=[
            AgentSkill.model_construct(
                name="broken",
                content="""---
description: Missing canonical name.
---

# Broken
""",
            )
        ]
    )

    with pytest.raises(ValueError) as excinfo:
        resolve_agent_config(config)

    assert "frontmatter is missing name" in str(excinfo.value)


def test_resolver_rejects_display_name_without_name():
    config = _config(
        skills=[
            AgentSkill.model_construct(
                name="broken",
                content="""---
display_name: Pretty label only.
---

# Broken
""",
            )
        ]
    )

    with pytest.raises(ValueError) as excinfo:
        resolve_agent_config(config)

    assert "frontmatter is missing name" in str(excinfo.value)


def test_resolver_rejects_skill_frontmatter_name_that_does_not_match_agent_skill_name():
    config = _config(
        skills=[
            AgentSkill.model_construct(
                name="Visible Skill",
                content="""---
name: Runtime Skill
---

# Runtime Skill
""",
            )
        ]
    )

    with pytest.raises(ValueError) as excinfo:
        resolve_agent_config(config)

    assert "frontmatter name must match AgentSkill.name" in str(excinfo.value)


def test_resolver_rejects_duplicate_enabled_skill_names():
    config = _config(
        skills=[
            _skill("github"),
            _skill("github"),
        ]
    )

    with pytest.raises(ValueError) as excinfo:
        resolve_agent_config(config)

    assert "Duplicate Skill name in AgentConfig: github" in str(excinfo.value)


def test_resolver_rejects_duplicate_enabled_mcp_server_names():
    config = _config(
        mcp_servers=[
            McpServerConfig(name="filesystem", transport="stdio", command="fs-one", enabled=True),
            McpServerConfig(name="filesystem", transport="stdio", command="fs-two", enabled=True),
        ]
    )

    with pytest.raises(ValueError) as excinfo:
        resolve_agent_config(config)

    assert "Duplicate MCP server name in AgentConfig: filesystem" in str(excinfo.value)


def test_resolver_has_no_repo_inputs():
    signature = inspect.signature(resolve_agent_config)

    assert list(signature.parameters) == ["config"]
