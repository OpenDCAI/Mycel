from __future__ import annotations

from collections.abc import Sequence

from config.agent_config_types import ResolvedSkill
from config.skill_document import parse_skill_document
from core.runtime.registry import ToolEntry, ToolMode, ToolRegistry, make_tool_schema


class SkillsService:
    def __init__(
        self,
        registry: ToolRegistry,
        skills: Sequence[ResolvedSkill] | None = None,
    ):
        self._skill_bodies: dict[str, str] = {}
        self._skill_descriptions: dict[str, str] = {}
        self._skill_files: dict[str, dict[str, str]] = {}
        self._load_skills(skills if skills is not None else ())
        self._register(registry)

    def _load_skills(self, skills: Sequence[ResolvedSkill]) -> None:
        for skill in skills:
            if not isinstance(skill, ResolvedSkill):
                raise TypeError("SkillsService requires ResolvedSkill items")
            document = parse_skill_document(skill.content, label="Skill content", require_description=True)
            if document.name != skill.name:
                raise ValueError("Skill frontmatter name must match ResolvedSkill.name")
            self._skill_bodies[skill.name] = document.body
            self._skill_descriptions[skill.name] = document.description
            self._skill_files[skill.name] = skill.files

    def _register(self, registry: ToolRegistry) -> None:
        if not self._skill_bodies:
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
        available_skills = sorted(self._skill_bodies)
        skills_list = "\n".join(f"- {name}: {self._skill_descriptions[name]}" for name in available_skills)
        skill_options = "; ".join(f"{name} - {self._skill_descriptions[name]}" for name in available_skills)

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
                    "description": f"Name of the skill to load. Available: {skill_options}",
                },
            },
            required=["skill_name"],
        )

    def _load_skill(self, skill_name: str) -> str:
        if skill_name not in self._skill_bodies:
            available = ", ".join(sorted(self._skill_bodies))
            raise ValueError(f"Skill '{skill_name}' not found. Available skills: {available}")

        content = self._skill_bodies[skill_name]
        return f"Loaded skill: {skill_name}\n\n{self._append_adjacent_files(content, self._skill_files[skill_name])}"

    @staticmethod
    def _append_adjacent_files(content: str, files: dict[str, str]) -> str:
        if not files:
            return content
        rendered_files = "\n\n".join(f"--- {path} ---\n{files[path]}" for path in sorted(files))
        return f"{content}\n\nAdjacent files:\n\n{rendered_files}"
