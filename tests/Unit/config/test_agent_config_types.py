from datetime import UTC, datetime

import pytest

from config.agent_config_types import AgentConfig, AgentRule, AgentSkill, AgentSubAgent, McpServerConfig, ResolvedSkill, SkillPackage


def test_resolved_skill_model_normalizes_file_paths() -> None:
    resolved_skill = ResolvedSkill(
        name="query-helper",
        content="---\nname: query-helper\n---\nUse exact terms.",
        files={"references\\query.md": "Prefer precise queries."},
    )

    assert resolved_skill.files == {"references/query.md": "Prefer precise queries."}


def test_resolved_skill_model_rejects_duplicate_file_paths_after_normalization() -> None:
    common = {
        "content": "---\nname: query-helper\n---\nUse exact terms.",
        "files": {
            "references\\query.md": "Windows-shaped key.",
            "references/query.md": "POSIX-shaped key.",
        },
    }

    with pytest.raises(ValueError, match="Skill files contain duplicate path after normalization: references/query.md"):
        ResolvedSkill(name="query-helper", **common)


def test_agent_skill_model_has_no_resolved_content() -> None:
    agent_skill = AgentSkill(skill_id="query-helper", package_id="package-1", name="query-helper")

    assert "content" not in agent_skill.model_dump()
    assert "files" not in agent_skill.model_dump()


def test_agent_skill_model_rejects_resolved_content_fields() -> None:
    with pytest.raises(ValueError, match="content"):
        AgentSkill.model_validate({"name": "query-helper", "skill_id": "skill-1", "package_id": "package-1", "content": "Use exact terms."})

    with pytest.raises(ValueError, match="files"):
        AgentSkill.model_validate(
            {
                "name": "query-helper",
                "skill_id": "skill-1",
                "package_id": "package-1",
                "files": {"references/query.md": "Use exact terms."},
            }
        )


def test_agent_config_model_rejects_unknown_fields() -> None:
    with pytest.raises(ValueError, match="skill_packages"):
        AgentConfig.model_validate(
            {
                "id": "cfg-1",
                "owner_user_id": "owner-1",
                "agent_user_id": "agent-1",
                "name": "Researcher",
                "skill_packages": [],
            }
        )


@pytest.mark.parametrize(
    ("model_cls", "kwargs"),
    [
        (AgentSkill, {"name": "query-helper"}),
        (AgentRule, {"name": "cite", "content": "cite sources"}),
        (AgentSubAgent, {"name": "worker"}),
        (McpServerConfig, {"name": "filesystem", "command": "fs"}),
    ],
)
def test_agent_config_child_models_reject_string_enabled(model_cls, kwargs) -> None:
    with pytest.raises(ValueError, match="enabled must be a boolean"):
        model_cls(enabled="false", **kwargs)


@pytest.mark.parametrize(
    ("model_cls", "kwargs"),
    [
        (AgentSkill, {"name": "query-helper"}),
        (AgentRule, {"name": "cite", "content": "cite sources"}),
        (AgentSubAgent, {"name": "worker"}),
        (McpServerConfig, {"name": "filesystem", "command": "fs"}),
    ],
)
def test_agent_config_child_models_reject_numeric_enabled(model_cls, kwargs) -> None:
    with pytest.raises(ValueError, match="enabled must be a boolean"):
        model_cls(enabled=1, **kwargs)


def test_skill_package_requires_package_identity_and_skill_md() -> None:
    package = SkillPackage(
        id="package-1",
        owner_user_id="owner-1",
        skill_id="skill-1",
        version="1.0.0",
        hash="sha256:abc",
        manifest={"files": [{"path": "references/query.md", "sha256": "def"}]},
        skill_md="---\nname: query-helper\n---\nUse exact terms.",
        files={"references\\query.md": "Prefer precise queries."},
        created_at=datetime(2026, 4, 25, tzinfo=UTC),
    )

    assert package.manifest["files"][0]["path"] == "references/query.md"
    assert package.files == {"references/query.md": "Prefer precise queries."}


def test_skill_package_rejects_blank_skill_md() -> None:
    common = {
        "id": "package-1",
        "owner_user_id": "owner-1",
        "skill_id": "skill-1",
        "version": "1.0.0",
        "hash": "sha256:abc",
        "manifest": {},
        "created_at": datetime(2026, 4, 25, tzinfo=UTC),
    }

    with pytest.raises(ValueError, match="skill_package.skill_md must not be blank"):
        SkillPackage(skill_md=" ", **common)
