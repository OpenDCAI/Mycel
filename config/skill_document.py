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
    description: str
    version: str | None


def parse_skill_document(
    content: str,
    *,
    label: str = "Skill document",
    require_description: bool = False,
    require_version: bool = False,
) -> SkillDocument:
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
    description = _optional_frontmatter_text(
        frontmatter,
        "description",
        label=label,
        required=require_description,
    )
    version = _optional_frontmatter_text(frontmatter, "version", label=label, required=require_version)
    return SkillDocument(
        frontmatter=frontmatter,
        body=content[match.end() :],
        name=name,
        description=description or "",
        version=version,
    )


def _frontmatter_text(frontmatter: dict[str, Any], key: str, *, label: str) -> str:
    value = frontmatter.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} frontmatter must include {key}")
    return value.strip()


def skill_description(document: SkillDocument, *, required: bool = False) -> str:
    if required and not document.description:
        raise ValueError("SKILL.md frontmatter must include description")
    return document.description


def skill_version(document: SkillDocument) -> str:
    if document.version is None:
        raise ValueError("SKILL.md frontmatter must include version")
    return document.version


def strip_skill_frontmatter(content: str) -> str:
    return parse_skill_document(content).body


def _optional_frontmatter_text(frontmatter: dict[str, Any], key: str, *, label: str, required: bool) -> str | None:
    value = frontmatter.get(key)
    if value is None and not required:
        return None
    if value is None:
        raise ValueError(f"{label} frontmatter must include {key}")
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} frontmatter {key} must be a string")
    return value.strip()
