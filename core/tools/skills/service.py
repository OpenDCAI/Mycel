from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml

from core.runtime.registry import ToolEntry, ToolMode, ToolRegistry, make_tool_schema


class SkillsService:
    def __init__(
        self,
        registry: ToolRegistry,
        skill_paths: Sequence[str | Path],
        enabled_skills: dict[str, bool] | None = None,
        inline_skills: Sequence[dict[str, Any]] | None = None,
    ):
        self.skill_paths = [Path(p).expanduser().resolve() for p in skill_paths]
        self.enabled_skills = enabled_skills or {}
        self._skills_index: dict[str, Path] = {}
        self._inline_skills: dict[str, str] = {}
        self._inline_skill_files: dict[str, dict[str, str]] = {}
        self._load_skills_index()
        self._load_inline_skills(inline_skills or [])
        self._register(registry)

    def _load_skills_index(self) -> None:
        for skill_dir in self.skill_paths:
            if not skill_dir.exists():
                continue
            for skill_file in skill_dir.rglob("SKILL.md"):
                content = skill_file.read_text(encoding="utf-8")
                metadata = self._parse_frontmatter(content)
                skill_name = metadata.get("name")
                if not skill_name:
                    raise ValueError(f"File Skill content must include frontmatter name: {skill_file}")
                self._skills_index[skill_name] = skill_file

    def _load_inline_skills(self, skills: Sequence[dict[str, Any]]) -> None:
        for skill in skills:
            content = skill.get("content")
            if not isinstance(content, str):
                raise ValueError("Inline Skill content must be a string")
            metadata = self._parse_frontmatter(content)
            if "name" not in metadata:
                raise ValueError("Inline Skill content must include frontmatter name")
            # @@@repo-backed-skill-index - DB-backed Agent configs do not have a
            # stable filesystem directory; keep their Skill content in memory
            # while exposing the same load_skill surface as disk-backed skills.
            skill_name = metadata["name"]
            self._inline_skills[skill_name] = content
            files = skill.get("files")
            if isinstance(files, dict):
                self._inline_skill_files[skill_name] = {str(path): str(body) for path, body in files.items()}
            elif files is not None:
                raise ValueError("Inline Skill files must be an object")

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
        if not self._skills_index and not self._inline_skills:
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
        available_skills = sorted({*self._skills_index.keys(), *self._inline_skills.keys()})
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
        if skill_name not in self._skills_index and skill_name not in self._inline_skills:
            available = ", ".join(sorted({*self._skills_index.keys(), *self._inline_skills.keys()}))
            raise ValueError(f"Skill '{skill_name}' not found. Available skills: {available}")

        if self.enabled_skills and skill_name in self.enabled_skills and not self.enabled_skills[skill_name]:
            raise ValueError(f"Skill '{skill_name}' is disabled in profile configuration.")

        if skill_name in self._inline_skills:
            content = re.sub(r"^---\s*\n.*?\n---\s*\n", "", self._inline_skills[skill_name], flags=re.DOTALL)
            return f"Loaded skill: {skill_name}\n\n{self._append_adjacent_files(content, self._inline_skill_files.get(skill_name, {}))}"

        skill_file = self._skills_index[skill_name]
        try:
            content = skill_file.read_text(encoding="utf-8")
        except OSError as exc:
            raise RuntimeError(f"Error loading Skill '{skill_name}': {exc}") from exc
        content = re.sub(r"^---\s*\n.*?\n---\s*\n", "", content, flags=re.DOTALL)
        return f"Loaded skill: {skill_name}\n\n{self._append_adjacent_files(content, self._read_adjacent_files(skill_file))}"

    @staticmethod
    def _append_adjacent_files(content: str, files: dict[str, str]) -> str:
        if not files:
            return content
        rendered_files = "\n\n".join(f"--- {path} ---\n{files[path]}" for path in sorted(files))
        return f"{content}\n\nAdjacent files:\n\n{rendered_files}"

    @staticmethod
    def _read_adjacent_files(skill_file: Path) -> dict[str, str]:
        files: dict[str, str] = {}
        skill_dir = skill_file.parent
        for path in sorted(skill_dir.rglob("*")):
            if not path.is_file() or path == skill_file:
                continue
            files[path.relative_to(skill_dir).as_posix()] = path.read_text(encoding="utf-8")
        return files
