from datetime import UTC, datetime

import pytest

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


def test_skill_models_reject_duplicate_file_paths_after_normalization() -> None:
    common = {
        "content": "---\nname: query-helper\n---\nUse exact terms.",
        "files": {
            "references\\query.md": "Windows-shaped key.",
            "references/query.md": "POSIX-shaped key.",
        },
    }

    with pytest.raises(ValueError, match="Skill files contain duplicate path after normalization: references/query.md"):
        Skill(
            id="query-helper",
            owner_user_id="owner-1",
            name="query-helper",
            created_at=datetime(2026, 4, 25, tzinfo=UTC),
            updated_at=datetime(2026, 4, 25, tzinfo=UTC),
            **common,
        )

    with pytest.raises(ValueError, match="Skill files contain duplicate path after normalization: references/query.md"):
        AgentSkill(name="query-helper", **common)
