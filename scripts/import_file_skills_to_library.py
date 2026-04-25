#!/usr/bin/env python3
"""Import file-backed Skills into the Library."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from config.agent_config_types import Skill, SkillPackage
from config.skill_document import SkillDocument, parse_skill_document, skill_description, skill_version
from config.skill_files import normalize_skill_file_entries
from config.skill_package import build_skill_package_hash, build_skill_package_manifest
from storage.runtime import build_storage_container
from storage.utils import generate_skill_id

FILE_IMPORT_SOURCE = {"kind": "file_import"}


def _skill_document(content: str) -> SkillDocument:
    document = parse_skill_document(content, label="SKILL.md")
    skill_description(document, required=True)
    skill_version(document)
    return document


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


def _find_skill_by_name(skills: list[Skill], skill_name: str) -> Skill | None:
    return next((skill for skill in skills if skill.name == skill_name), None)


def import_skills(owner_user_id: str, library_dir: Path) -> int:
    repo = build_storage_container().skill_repo()
    skills_root = library_dir / "skills"
    if not skills_root.is_dir():
        raise RuntimeError(f"Skill directory not found: {skills_root}")

    count = 0
    for skill_dir in sorted(path for path in skills_root.iterdir() if path.is_dir()):
        content = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        document = _skill_document(content)
        skill_name = document.name
        existing = _find_skill_by_name(repo.list_for_owner(owner_user_id), skill_name)
        now = datetime.now(UTC)
        skill_id = existing.id if existing is not None else generate_skill_id()
        if existing is None and repo.get_by_id(owner_user_id, skill_id) is not None:
            raise RuntimeError("Generated Skill id already exists")
        version = skill_version(document)
        files = _read_files(skill_dir)
        package_hash = build_skill_package_hash(content, files)
        skill = repo.upsert(
            Skill(
                id=skill_id,
                owner_user_id=owner_user_id,
                name=skill_name,
                description=skill_description(document, required=True),
                source=dict(FILE_IMPORT_SOURCE),
                created_at=getattr(existing, "created_at", now),
                updated_at=now,
            )
        )
        package = repo.create_package(
            SkillPackage(
                id=package_hash.removeprefix("sha256:"),
                owner_user_id=owner_user_id,
                skill_id=skill.id,
                version=version,
                hash=package_hash,
                manifest=build_skill_package_manifest(content, files),
                skill_md=content,
                files=files,
                source=dict(FILE_IMPORT_SOURCE),
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
