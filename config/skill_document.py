from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import yaml

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


@dataclass(frozen=True)
class SkillDocument:
    frontmatter: dict[str, Any]
    body: str
    name: str


def parse_skill_document(content: str, *, label: str = "Skill document") -> SkillDocument:
    match = _FRONTMATTER_RE.match(content)
    if match is None:
        raise ValueError(f"{label} must be a SKILL.md document with frontmatter")
    try:
        frontmatter = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"{label} frontmatter must be valid YAML") from exc
    if not isinstance(frontmatter, dict):
        raise ValueError(f"{label} frontmatter must be a mapping")
    name = _frontmatter_text(frontmatter, "name", label=label)
    return SkillDocument(frontmatter=frontmatter, body=content[match.end() :], name=name)


def skill_description(document: SkillDocument, *, required: bool = False) -> str:
    value = document.frontmatter.get("description")
    if value is None and not required:
        return ""
    return _frontmatter_text(document.frontmatter, "description", label="SKILL.md")


def skill_version(document: SkillDocument) -> str:
    if "version" not in document.frontmatter:
        raise ValueError("SKILL.md frontmatter must include version")
    value = document.frontmatter["version"]
    if not isinstance(value, str) or not value.strip():
        raise ValueError("SKILL.md frontmatter version must be a string")
    return value.strip()


def strip_skill_frontmatter(content: str) -> str:
    return parse_skill_document(content).body


def _frontmatter_text(frontmatter: dict[str, Any], key: str, *, label: str) -> str:
    value = frontmatter.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} frontmatter must include {key}")
    return value.strip()
