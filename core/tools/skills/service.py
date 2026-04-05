"""Skills Service - registers load_skill tool with ToolRegistry.

Tools:
- load_skill: Progressive disclosure of specialized capabilities

Uses dynamic schema (callable) to reflect current skill index on each call.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path

from core.runtime.registry import ToolEntry, ToolMode, ToolRegistry


class SkillsService:
    """Registers load_skill tool into ToolRegistry with dynamic schema."""

    def __init__(
        self,
        registry: ToolRegistry,
        skill_paths: Sequence[str | Path],
        enabled_skills: dict[str, bool] | None = None,
    ):
        self.skill_paths = [Path(p).expanduser().resolve() for p in skill_paths]
        self.enabled_skills = enabled_skills or {}
        self._skills_index: dict[str, Path] = {}
        self._load_skills_index()
        self._register(registry)

    def _load_skills_index(self) -> None:
        for skill_dir in self.skill_paths:
            if not skill_dir.exists():
                continue
            for skill_file in skill_dir.rglob("SKILL.md"):
                try:
                    content = skill_file.read_text(encoding="utf-8")
                    metadata = self._parse_frontmatter(content)
                    if "name" in metadata:
                        self._skills_index[metadata["name"]] = skill_file
                except Exception:
                    pass

    @staticmethod
    def _parse_frontmatter(content: str) -> dict[str, str]:
        match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
        if not match:
            return {}
        metadata = {}
        for line in match.group(1).split("\n"):
            if ":" in line:
                key, value = line.split(":", 1)
                metadata[key.strip()] = value.strip()
        return metadata

    def _register(self, registry: ToolRegistry) -> None:
        if not self._skills_index:
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
        available_skills = list(self._skills_index.keys())
        skills_list = "\n".join(f"- {name}" for name in available_skills)

        return {
            "name": "load_skill",
            "description": (
                f"Load a skill for domain-specific guidance. "
                f"Use when you need specialized workflows (TDD, debugging, git). "
                f"Skills are loaded on-demand to save context.\n\n"
                f"Available skills:\n{skills_list}"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "skill_name": {
                        "type": "string",
                        "description": f"Name of the skill to load. Available: {', '.join(self._skills_index.keys())}",
                    },
                },
                "required": ["skill_name"],
            },
        }

    def _load_skill(self, skill_name: str) -> str:
        if skill_name not in self._skills_index:
            available = ", ".join(self._skills_index.keys())
            return f"Skill '{skill_name}' not found.\nAvailable skills: {available}"

        if self.enabled_skills and skill_name in self.enabled_skills and not self.enabled_skills[skill_name]:
            return f"Skill '{skill_name}' is disabled in profile configuration."

        skill_file = self._skills_index[skill_name]
        try:
            content = skill_file.read_text(encoding="utf-8")
            content = re.sub(r"^---\s*\n.*?\n---\s*\n", "", content, flags=re.DOTALL)
            return f"Loaded skill: {skill_name}\n\n{content}"
        except Exception as e:
            return f"Error loading skill '{skill_name}': {e}"
