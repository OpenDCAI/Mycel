from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

import yaml

from config.skill_files import normalize_skill_file_map
from core.runtime.registry import ToolEntry, ToolMode, ToolRegistry, make_tool_schema


class SkillsService:
    def __init__(
        self,
        registry: ToolRegistry,
        skills: Sequence[dict[str, Any]] | None = None,
        enabled_skills: dict[str, bool] | None = None,
    ):
        self.enabled_skills = enabled_skills or {}
        self._skills: dict[str, str] = {}
        self._skill_files: dict[str, dict[str, str]] = {}
        self._load_skills(skills or [])
        self._register(registry)

    def _load_skills(self, skills: Sequence[dict[str, Any]]) -> None:
        for skill in skills:
            content = skill.get("content")
            if not isinstance(content, str):
                raise ValueError("Skill content must be a string")
            metadata = self._parse_frontmatter(content)
            if "name" not in metadata:
                raise ValueError("Skill content must include frontmatter name")
            skill_name = metadata["name"]
            self._skills[skill_name] = content
            files = skill.get("files")
            if isinstance(files, dict):
                self._skill_files[skill_name] = normalize_skill_file_map(files, context="Skill files")
            elif files is not None:
                raise ValueError("Skill files must be an object")

    @staticmethod
    def _parse_frontmatter(content: str) -> dict[str, str]:
        match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
        if not match:
            return {}
        metadata = yaml.safe_load(match.group(1)) or {}
        if not isinstance(metadata, dict):
            raise ValueError("Skill frontmatter must be a mapping")
        result: dict[str, str] = {}
        for key, value in metadata.items():
            if isinstance(key, str) and isinstance(value, str):
                result[key.strip()] = value.strip()
        return result

    def _register(self, registry: ToolRegistry) -> None:
        if not self._skills:
            return

        registry.register(
            ToolEntry(
                name="load_skill",
                mode=ToolMode.INLINE,
                schema=self._get_schema,
                handler=self._load_skill,
                source="SkillsService",
                is_concurrency_safe=True,
                is_read_only=True,
            )
        )

    def _get_schema(self) -> dict:
        available_skills = sorted(self._skills)
        skills_list = "\n".join(f"- {name}" for name in available_skills)

        return make_tool_schema(
            name="load_skill",
            description=(
                f"Load a skill for domain-specific guidance. "
                f"Use when you need specialized workflows (TDD, debugging, git). "
                f"Skills are loaded on-demand to save context.\n\n"
                f"Available skills:\n{skills_list}"
            ),
            properties={
                "skill_name": {
                    "type": "string",
                    "description": f"Name of the skill to load. Available: {', '.join(available_skills)}",
                },
            },
            required=["skill_name"],
        )

    def _load_skill(self, skill_name: str) -> str:
        if skill_name not in self._skills:
            available = ", ".join(sorted(self._skills))
            raise ValueError(f"Skill '{skill_name}' not found. Available skills: {available}")

        if self.enabled_skills and skill_name in self.enabled_skills and not self.enabled_skills[skill_name]:
            raise ValueError(f"Skill '{skill_name}' is disabled in profile configuration.")

        content = re.sub(r"^---\s*\n.*?\n---\s*\n", "", self._skills[skill_name], flags=re.DOTALL)
        return f"Loaded skill: {skill_name}\n\n{self._append_adjacent_files(content, self._skill_files.get(skill_name, {}))}"

    @staticmethod
    def _append_adjacent_files(content: str, files: dict[str, str]) -> str:
        if not files:
            return content
        rendered_files = "\n\n".join(f"--- {path} ---\n{files[path]}" for path in sorted(files))
        return f"{content}\n\nAdjacent files:\n\n{rendered_files}"
