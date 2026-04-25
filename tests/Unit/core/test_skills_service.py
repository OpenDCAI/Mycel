from typing import cast

import pytest

from core.runtime.registry import ToolRegistry
from core.tools.skills.service import SkillsService


def test_load_file_skill_returns_adjacent_files(tmp_path) -> None:
    skill_dir = tmp_path / "query-helper"
    refs_dir = skill_dir / "references"
    refs_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: query-helper\n---\nUse exact terms.", encoding="utf-8")
    (refs_dir / "query.md").write_text("Prefer precise queries.", encoding="utf-8")
    registry = ToolRegistry()

    SkillsService(registry=registry, skill_paths=[tmp_path])

    entry = registry.get("load_skill")
    assert entry is not None

    result = cast(str, entry.handler("query-helper"))

    assert "Loaded skill: query-helper" in result
    assert "Use exact terms." in result
    assert "references/query.md" in result
    assert "Prefer precise queries." in result


def test_file_skill_frontmatter_uses_yaml_parser(tmp_path) -> None:
    skill_dir = tmp_path / "query-helper"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text('---\nname: "query-helper"\n---\nUse exact terms.', encoding="utf-8")
    registry = ToolRegistry()

    SkillsService(registry=registry, skill_paths=[tmp_path])

    entry = registry.get("load_skill")
    assert entry is not None
    assert entry.handler("query-helper") == "Loaded skill: query-helper\n\nUse exact terms."


def test_load_missing_skill_fails_loudly(tmp_path) -> None:
    skill_dir = tmp_path / "query-helper"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: query-helper\n---\nUse exact terms.", encoding="utf-8")
    registry = ToolRegistry()
    SkillsService(registry=registry, skill_paths=[tmp_path])

    entry = registry.get("load_skill")
    assert entry is not None
    with pytest.raises(ValueError, match="Skill 'missing' not found"):
        entry.handler("missing")


def test_load_file_skill_read_error_fails_loudly(tmp_path) -> None:
    skill_dir = tmp_path / "query-helper"
    skill_dir.mkdir()
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text("---\nname: query-helper\n---\nUse exact terms.", encoding="utf-8")
    registry = ToolRegistry()
    SkillsService(registry=registry, skill_paths=[tmp_path])
    skill_file.unlink()

    entry = registry.get("load_skill")
    assert entry is not None
    with pytest.raises(RuntimeError, match="Error loading Skill 'query-helper'"):
        entry.handler("query-helper")


def test_inline_skill_without_frontmatter_name_fails_loudly() -> None:
    registry = ToolRegistry()

    with pytest.raises(ValueError, match="Inline Skill content must include frontmatter name"):
        SkillsService(
            registry=registry,
            skill_paths=[],
            inline_skills=[
                {
                    "name": "query-helper",
                    "content": "Use exact terms.",
                }
            ],
        )


def test_inline_skill_without_string_content_fails_loudly() -> None:
    registry = ToolRegistry()

    with pytest.raises(ValueError, match="Inline Skill content must be a string"):
        SkillsService(
            registry=registry,
            skill_paths=[],
            inline_skills=[
                {
                    "name": "query-helper",
                    "content": None,
                }
            ],
        )


def test_inline_skill_files_must_be_an_object() -> None:
    registry = ToolRegistry()

    with pytest.raises(ValueError, match="Inline Skill files must be an object"):
        SkillsService(
            registry=registry,
            skill_paths=[],
            inline_skills=[
                {
                    "name": "query-helper",
                    "content": "---\nname: query-helper\n---\nUse exact terms.",
                    "files": ["references/query.md"],
                }
            ],
        )


def test_file_skill_without_frontmatter_name_fails_loudly(tmp_path) -> None:
    skill_dir = tmp_path / "broken-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("Use exact terms.", encoding="utf-8")
    registry = ToolRegistry()

    with pytest.raises(ValueError, match="File Skill content must include frontmatter name"):
        SkillsService(registry=registry, skill_paths=[tmp_path])


def test_load_inline_skill_returns_adjacent_files() -> None:
    registry = ToolRegistry()
    SkillsService(
        registry=registry,
        skill_paths=[],
        inline_skills=[
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


def test_load_inline_skill_normalizes_adjacent_file_paths() -> None:
    registry = ToolRegistry()
    SkillsService(
        registry=registry,
        skill_paths=[],
        inline_skills=[
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
