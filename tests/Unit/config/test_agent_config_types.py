from datetime import UTC, datetime

import pytest

from config.agent_config_types import AgentConfig, AgentRule, AgentSkill, AgentSubAgent, McpServerConfig, ResolvedSkill, SkillPackage


def test_resolved_skill_model_normalizes_file_paths() -> None:
    resolved_skill = ResolvedSkill(
        id="query-helper",
        name="query-helper",
        version="1.0.0",
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
        ResolvedSkill(id="query-helper", name="query-helper", **common)


def test_resolved_skill_model_rejects_blank_version() -> None:
    with pytest.raises(ValueError, match="resolved_skill.version must not be blank"):
        ResolvedSkill(
            id="query-helper",
            name="query-helper",
            version=" ",
            content="---\nname: query-helper\n---\nUse exact terms.",
        )


def test_resolved_skill_model_requires_id() -> None:
    with pytest.raises(ValueError) as excinfo:
        ResolvedSkill.model_validate(
            {
                "name": "query-helper",
                "version": "1.0.0",
                "content": "---\nname: query-helper\n---\nUse exact terms.",
            }
        )

    assert "id" in str(excinfo.value)


def test_resolved_skill_model_rejects_blank_id() -> None:
    with pytest.raises(ValueError, match="resolved_skill.id must not be blank"):
        ResolvedSkill(
            id=" ",
            name="query-helper",
            version="1.0.0",
            content="---\nname: query-helper\n---\nUse exact terms.",
        )


def test_agent_skill_model_has_no_resolved_content() -> None:
    agent_skill = AgentSkill(skill_id="query-helper", package_id="package-1")

    assert "name" not in agent_skill.model_dump()
    assert "description" not in agent_skill.model_dump()
    assert "content" not in agent_skill.model_dump()
    assert "files" not in agent_skill.model_dump()


def test_agent_skill_model_requires_library_skill_and_package_identity() -> None:
    with pytest.raises(ValueError) as missing_skill_excinfo:
        AgentSkill.model_validate({"package_id": "package-1"})
    with pytest.raises(ValueError) as missing_package_excinfo:
        AgentSkill.model_validate({"skill_id": "query-helper"})

    assert "skill_id" in str(missing_skill_excinfo.value)
    assert "package_id" in str(missing_package_excinfo.value)


def test_agent_skill_model_rejects_blank_library_skill_and_package_identity() -> None:
    with pytest.raises(ValueError, match="agent_skill.skill_id must not be blank"):
        AgentSkill(skill_id=" ", package_id="package-1")
    with pytest.raises(ValueError, match="agent_skill.package_id must not be blank"):
        AgentSkill(skill_id="query-helper", package_id=" ")


def test_agent_skill_model_rejects_resolved_content_fields() -> None:
    with pytest.raises(ValueError, match="content"):
        AgentSkill.model_validate(
            {
                "skill_id": "skill-1",
                "package_id": "package-1",
                "content": "Use exact terms.",
            }
        )

    with pytest.raises(ValueError, match="files"):
        AgentSkill.model_validate(
            {
                "skill_id": "skill-1",
                "package_id": "package-1",
                "files": {"references/query.md": "Use exact terms."},
            }
        )


def test_agent_skill_model_rejects_package_version() -> None:
    with pytest.raises(ValueError, match="version"):
        AgentSkill.model_validate(
            {
                "skill_id": "skill-1",
                "package_id": "package-1",
                "version": "1.0.0",
            }
        )


def test_agent_skill_model_rejects_package_source() -> None:
    with pytest.raises(ValueError, match="source"):
        AgentSkill.model_validate(
            {
                "skill_id": "skill-1",
                "package_id": "package-1",
                "name": "query-helper",
                "source": {"source_version": "1.0.0"},
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
                "version": "1.0.0",
                "skill_packages": [],
            }
        )


def test_agent_config_model_requires_version() -> None:
    with pytest.raises(ValueError) as excinfo:
        AgentConfig.model_validate(
            {
                "id": "cfg-1",
                "owner_user_id": "owner-1",
                "agent_user_id": "agent-1",
                "name": "Researcher",
            }
        )

    assert "version" in str(excinfo.value)


def test_agent_config_model_rejects_blank_version() -> None:
    with pytest.raises(ValueError, match="agent_config.version must not be blank"):
        AgentConfig(
            id="cfg-1",
            owner_user_id="owner-1",
            agent_user_id="agent-1",
            name="Researcher",
            version=" ",
        )


@pytest.mark.parametrize(
    ("model_cls", "kwargs"),
    [
        (AgentSkill, {"skill_id": "query-helper", "package_id": "package-1"}),
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
        (AgentSkill, {"skill_id": "query-helper", "package_id": "package-1"}),
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


@pytest.mark.parametrize(
    ("model_cls", "payload"),
    [
        (
            SkillPackage,
            {
                "id": "package-1",
                "owner_user_id": "owner-1",
                "skill_id": "skill-1",
                "hash": "sha256:abc",
                "skill_md": "---\nname: query-helper\n---\nUse exact terms.",
                "created_at": datetime(2026, 4, 25, tzinfo=UTC),
            },
        ),
        (ResolvedSkill, {"id": "query-helper", "name": "query-helper", "content": "---\nname: query-helper\n---\nUse exact terms."}),
    ],
)
def test_skill_package_and_runtime_skill_models_require_version(model_cls, payload) -> None:
    with pytest.raises(ValueError) as excinfo:
        model_cls.model_validate(payload)

    assert "version" in str(excinfo.value)
