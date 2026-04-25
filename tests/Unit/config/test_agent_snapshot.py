from config.agent_config_resolver import resolve_agent_config
from config.agent_config_types import AgentConfig, AgentSkill, SkillPackage
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
                    skill_id="github",
                    package_id="github-package",
                    name="github",
                    version="1.0.0",
                )
            ],
        ),
        skill_repo=type(
            "_SkillRepo",
            (),
            {
                "get_package": lambda self, _owner_user_id, package_id: SkillPackage(
                    id=package_id,
                    owner_user_id="owner-1",
                    skill_id="github",
                    version="1.0.0",
                    hash="sha256:github",
                    skill_md="---\nname: github\n---\n\n# GitHub\n",
                    files={"references/query.md": "Prefer precise queries."},
                    created_at="2026-04-25T00:00:00+00:00",
                )
            },
        )(),
    )

    snapshot = snapshot_from_resolved_config(resolved)
    payload = snapshot.model_dump(mode="json")

    assert payload["schema_version"] == "agent-snapshot/v1"
    assert payload["agent"]["id"] == "cfg-1"
    assert payload["agent"]["skills"][0]["name"] == "github"
    assert payload["agent"]["skills"][0]["files"] == {"references/query.md": "Prefer precise queries."}
    assert "owner_user_id" not in payload["agent"]
    assert "agent_user_id" not in payload["agent"]
