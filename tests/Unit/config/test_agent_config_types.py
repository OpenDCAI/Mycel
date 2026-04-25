from datetime import UTC, datetime

from config.agent_config_types import AgentSkill, Skill


def test_skill_models_normalize_file_paths() -> None:
    skill = Skill(
        id="query-helper",
        owner_user_id="owner-1",
        name="query-helper",
        content="---\nname: query-helper\n---\nUse exact terms.",
        files={"references\\query.md": "Prefer precise queries."},
        created_at=datetime(2026, 4, 25, tzinfo=UTC),
        updated_at=datetime(2026, 4, 25, tzinfo=UTC),
    )
    agent_skill = AgentSkill(
        name="query-helper",
        content="---\nname: query-helper\n---\nUse exact terms.",
        files={"references\\query.md": "Prefer precise queries."},
    )

    assert skill.files == {"references/query.md": "Prefer precise queries."}
    assert agent_skill.files == {"references/query.md": "Prefer precise queries."}
