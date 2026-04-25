from config.agent_config_resolver import resolve_agent_config
from config.agent_config_types import AgentConfig, AgentSkill
from config.agent_snapshot import snapshot_from_resolved_config


def test_snapshot_contains_resolved_agent_config_only():
    resolved = resolve_agent_config(
        AgentConfig(
            id="cfg-1",
            owner_user_id="owner-1",
            agent_user_id="agent-1",
            name="Researcher",
            skills=[
                AgentSkill(
                    name="github",
                    content="""---
name: github
---

# GitHub
""",
                    files={"references/query.md": "Prefer precise queries."},
                )
            ],
        )
    )

    snapshot = snapshot_from_resolved_config(resolved)
    payload = snapshot.model_dump(mode="json")

    assert payload["schema_version"] == "agent-snapshot/v1"
    assert payload["agent"]["id"] == "cfg-1"
    assert payload["agent"]["skills"][0]["name"] == "github"
    assert payload["agent"]["skills"][0]["files"] == {"references/query.md": "Prefer precise queries."}
    assert "owner_user_id" not in payload["agent"]
    assert "agent_user_id" not in payload["agent"]
