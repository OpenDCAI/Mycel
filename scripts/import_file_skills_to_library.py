#!/usr/bin/env python3
"""Import file-backed Skills into the Library."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from config.agent_config_types import Skill, SkillPackage
from config.skill_files import normalize_skill_file_entries
from config.skill_package import build_skill_package_hash, build_skill_package_manifest
from storage.runtime import build_storage_container


def _frontmatter(content: str) -> dict[str, Any]:
    if not content.startswith("---"):
        raise ValueError("SKILL.md must start with YAML frontmatter")
    parts = content.split("---", 2)
    if len(parts) < 3:
        raise ValueError("SKILL.md frontmatter is not closed")
    metadata = yaml.safe_load(parts[1]) or {}
    if not isinstance(metadata, dict):
        raise ValueError("SKILL.md frontmatter must be a mapping")
    if not str(metadata.get("name") or "").strip():
        raise ValueError("SKILL.md frontmatter must include name")
    return metadata


def _read_files(skill_dir: Path) -> dict[str, str]:
    file_entries: list[tuple[str, str]] = []
    for path in sorted(skill_dir.rglob("*")):
        if not path.is_file() or path.name == "SKILL.md":
            continue
        try:
            file_entries.append((path.relative_to(skill_dir).as_posix(), path.read_text(encoding="utf-8")))
        except UnicodeDecodeError as exc:
            raise RuntimeError(f"Skill adjacent file could not be read: {path}") from exc
    return normalize_skill_file_entries(file_entries, context="File Skill files")


def import_skills(owner_user_id: str, library_dir: Path) -> int:
    repo = build_storage_container().skill_repo()
    skills_root = library_dir / "skills"
    if not skills_root.is_dir():
        raise RuntimeError(f"Skill directory not found: {skills_root}")

    count = 0
    for skill_dir in sorted(path for path in skills_root.iterdir() if path.is_dir()):
        content = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        metadata = _frontmatter(content)
        skill_name = str(metadata["name"]).strip()
        existing = repo.get_by_id(owner_user_id, skill_dir.name)
        if existing is not None and existing.name != skill_name:
            raise ValueError("SKILL.md frontmatter name must match existing Skill name")
        for skill in repo.list_for_owner(owner_user_id):
            if skill.name == skill_name and skill.id != skill_dir.name:
                raise ValueError("Skill name already exists under a different Library id")
        now = datetime.now(UTC)
        files = _read_files(skill_dir)
        package_hash = build_skill_package_hash(content, files)
        skill = repo.upsert(
            Skill(
                id=skill_dir.name,
                owner_user_id=owner_user_id,
                name=skill_name,
                description=str(metadata.get("description") or ""),
                source={"file_skill_dir": str(skill_dir)},
                created_at=now,
                updated_at=now,
            )
        )
        package = repo.create_package(
            SkillPackage(
                id=package_hash.removeprefix("sha256:"),
                owner_user_id=owner_user_id,
                skill_id=skill.id,
                version=str(metadata.get("version") or "0.1.0"),
                hash=package_hash,
                manifest=build_skill_package_manifest(content, files),
                skill_md=content,
                files=files,
                source={"file_skill_dir": str(skill_dir)},
                created_at=now,
            )
        )
        repo.select_package(owner_user_id, skill.id, package.id)
        count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--owner-user-id", required=True)
    parser.add_argument("--library-dir", type=Path, required=True)
    args = parser.parse_args()

    count = import_skills(args.owner_user_id, args.library_dir.expanduser().resolve())
    print(f"Imported {count} skills")


if __name__ == "__main__":
    main()
