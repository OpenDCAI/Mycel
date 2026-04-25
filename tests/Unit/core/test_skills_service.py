import inspect
from typing import cast

import pytest

from core.runtime.registry import ToolRegistry
from core.tools.skills.service import SkillsService


def test_skills_service_has_no_filesystem_skill_index() -> None:
    source = inspect.getsource(SkillsService)

    assert "skill_paths" not in source
    assert "rglob" not in source
    assert "SKILL.md" not in source


def test_skills_service_does_not_register_without_skills() -> None:
    registry = ToolRegistry()

    SkillsService(registry=registry)

    assert registry.get("load_skill") is None


def test_skill_frontmatter_uses_yaml_parser() -> None:
    registry = ToolRegistry()

    SkillsService(
        registry=registry,
        skills=[
            {
                "name": "query-helper",
                "content": '---\nname: "query-helper"\n---\nUse exact terms.',
            }
        ],
    )

    entry = registry.get("load_skill")
    assert entry is not None
    assert entry.handler("query-helper") == "Loaded skill: query-helper\n\nUse exact terms."


def test_load_missing_skill_fails_loudly() -> None:
    registry = ToolRegistry()
    SkillsService(
        registry=registry,
        skills=[
            {
                "name": "query-helper",
                "content": "---\nname: query-helper\n---\nUse exact terms.",
            }
        ],
    )

    entry = registry.get("load_skill")
    assert entry is not None
    with pytest.raises(ValueError, match="Skill 'missing' not found"):
        entry.handler("missing")


def test_skill_without_frontmatter_name_fails_loudly() -> None:
    registry = ToolRegistry()

    with pytest.raises(ValueError, match="Skill content must include frontmatter name"):
        SkillsService(
            registry=registry,
            skills=[
                {
                    "name": "query-helper",
                    "content": "Use exact terms.",
                }
            ],
        )


def test_skill_without_string_content_fails_loudly() -> None:
    registry = ToolRegistry()

    with pytest.raises(ValueError, match="Skill content must be a string"):
        SkillsService(
            registry=registry,
            skills=[
                {
                    "name": "query-helper",
                    "content": None,
                }
            ],
        )


def test_skill_files_must_be_an_object() -> None:
    registry = ToolRegistry()

    with pytest.raises(ValueError, match="Skill files must be an object"):
        SkillsService(
            registry=registry,
            skills=[
                {
                    "name": "query-helper",
                    "content": "---\nname: query-helper\n---\nUse exact terms.",
                    "files": ["references/query.md"],
                }
            ],
        )


def test_load_skill_returns_adjacent_files() -> None:
    registry = ToolRegistry()
    SkillsService(
        registry=registry,
        skills=[
            {
                "name": "query-helper",
                "content": "---\nname: query-helper\n---\nUse exact terms.",
                "files": {"references/query.md": "Prefer precise queries."},
            }
        ],
    )

    entry = registry.get("load_skill")
    assert entry is not None

    result = cast(str, entry.handler("query-helper"))

    assert "Loaded skill: query-helper" in result
    assert "Use exact terms." in result
    assert "references/query.md" in result
    assert "Prefer precise queries." in result


def test_load_skill_normalizes_adjacent_file_paths() -> None:
    registry = ToolRegistry()
    SkillsService(
        registry=registry,
        skills=[
            {
                "name": "query-helper",
                "content": "---\nname: query-helper\n---\nUse exact terms.",
                "files": {"references\\query.md": "Prefer precise queries."},
            }
        ],
    )

    entry = registry.get("load_skill")
    assert entry is not None

    result = cast(str, entry.handler("query-helper"))

    assert "--- references/query.md ---" in result
    assert "references\\query.md" not in result


def test_skill_rejects_adjacent_file_path_collision() -> None:
    registry = ToolRegistry()

    with pytest.raises(ValueError, match="Skill files contain duplicate path after normalization: references/query.md"):
        SkillsService(
            registry=registry,
            skills=[
                {
                    "name": "query-helper",
                    "content": "---\nname: query-helper\n---\nUse exact terms.",
                    "files": {
                        "references\\query.md": "Windows-shaped key.",
                        "references/query.md": "POSIX-shaped key.",
                    },
                }
            ],
        )
