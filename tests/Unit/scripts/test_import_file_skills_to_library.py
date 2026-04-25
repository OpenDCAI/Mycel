from __future__ import annotations

import inspect
from datetime import UTC, datetime
from os import PathLike
from pathlib import Path, PurePosixPath, PureWindowsPath
from types import SimpleNamespace

import pytest

from config.agent_config_types import Skill, SkillPackage
from scripts import import_file_skills_to_library


class _MemorySkillRepo:
    def __init__(self, existing: Skill | None = None) -> None:
        self.existing = existing
        self.saved: list[Skill] = []
        self.packages: list[SkillPackage] = []
        self.selected: list[tuple[str, str, str]] = []

    def list_for_owner(self, owner_user_id: str) -> list[Skill]:
        if self.existing and self.existing.owner_user_id == owner_user_id:
            return [self.existing]
        return []

    def get_by_id(self, owner_user_id: str, skill_id: str) -> Skill | None:
        if self.existing and self.existing.owner_user_id == owner_user_id and self.existing.id == skill_id:
            return self.existing
        return None

    def upsert(self, skill: Skill) -> Skill:
        self.saved.append(skill)
        return skill

    def create_package(self, package: SkillPackage) -> SkillPackage:
        self.packages.append(package)
        return package

    def select_package(self, owner_user_id: str, skill_id: str, package_id: str) -> None:
        self.selected.append((owner_user_id, skill_id, package_id))


def test_import_file_skill_rejects_name_drift_for_existing_skill_id(monkeypatch: pytest.MonkeyPatch, tmp_path):
    library_dir = tmp_path / "library"
    skill_dir = library_dir / "skills" / "same-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: Renamed Skill\ndescription: Renamed\nversion: 1.0.0\n---\nBody", encoding="utf-8")
    repo = _MemorySkillRepo(
        Skill(
            id="same-skill",
            owner_user_id="owner-1",
            name="Original Skill",
            created_at=datetime(2026, 4, 24, tzinfo=UTC),
            updated_at=datetime(2026, 4, 24, tzinfo=UTC),
        )
    )
    monkeypatch.setattr(import_file_skills_to_library, "build_storage_container", lambda: SimpleNamespace(skill_repo=lambda: repo))

    with pytest.raises(ValueError, match="frontmatter name must match existing Skill name"):
        import_file_skills_to_library.import_skills("owner-1", library_dir)

    assert repo.saved == []


def test_import_file_skill_rejects_same_name_under_different_skill_id(monkeypatch: pytest.MonkeyPatch, tmp_path):
    library_dir = tmp_path / "library"
    skill_dir = library_dir / "skills" / "new-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: Shared Skill\ndescription: Shared\nversion: 1.0.0\n---\nBody", encoding="utf-8")
    repo = _MemorySkillRepo(
        Skill(
            id="original-skill",
            owner_user_id="owner-1",
            name="Shared Skill",
            created_at=datetime(2026, 4, 24, tzinfo=UTC),
            updated_at=datetime(2026, 4, 24, tzinfo=UTC),
        )
    )
    monkeypatch.setattr(import_file_skills_to_library, "build_storage_container", lambda: SimpleNamespace(skill_repo=lambda: repo))

    with pytest.raises(ValueError, match="Skill name already exists under a different Library id"):
        import_file_skills_to_library.import_skills("owner-1", library_dir)

    assert repo.saved == []


def test_import_file_skill_rejects_unreadable_adjacent_file(monkeypatch: pytest.MonkeyPatch, tmp_path):
    library_dir = tmp_path / "library"
    skill_dir = library_dir / "skills" / "new-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: New Skill\ndescription: New\nversion: 1.0.0\n---\nBody", encoding="utf-8")
    (skill_dir / "broken.bin").write_bytes(b"\xff\xfe\xfa")
    repo = _MemorySkillRepo()
    monkeypatch.setattr(import_file_skills_to_library, "build_storage_container", lambda: SimpleNamespace(skill_repo=lambda: repo))

    with pytest.raises(RuntimeError, match="Skill adjacent file could not be read"):
        import_file_skills_to_library.import_skills("owner-1", library_dir)

    assert repo.saved == []


def test_import_file_skill_stores_adjacent_files_as_posix_paths(monkeypatch: pytest.MonkeyPatch, tmp_path):
    library_dir = tmp_path / "library"
    skill_dir = library_dir / "skills" / "new-skill"
    refs_dir = skill_dir / "references"
    refs_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: New Skill\ndescription: New\nversion: 1.0.0\n---\nBody", encoding="utf-8")
    (refs_dir / "query.md").write_text("Use exact queries.", encoding="utf-8")
    repo = _MemorySkillRepo()
    original_relative_to = Path.relative_to

    def windows_relative_to(self: Path, *other: str | PathLike[str]) -> PureWindowsPath:
        relative_path = original_relative_to(self, *other)
        return PureWindowsPath(*relative_path.parts)

    monkeypatch.setattr(Path, "relative_to", windows_relative_to)
    monkeypatch.setattr(import_file_skills_to_library, "build_storage_container", lambda: SimpleNamespace(skill_repo=lambda: repo))

    import_file_skills_to_library.import_skills("owner-1", library_dir)

    assert repo.saved[0].id == "new-skill"
    assert repo.packages[0].skill_id == "new-skill"
    assert repo.packages[0].version == "1.0.0"
    assert repo.packages[0].skill_md == "---\nname: New Skill\ndescription: New\nversion: 1.0.0\n---\nBody"
    assert repo.packages[0].manifest["files"][0]["path"] == "references/query.md"
    assert repo.selected == [("owner-1", "new-skill", repo.packages[0].id)]


def test_import_file_skill_does_not_store_local_skill_path(monkeypatch: pytest.MonkeyPatch, tmp_path):
    library_dir = tmp_path / "library"
    skill_dir = library_dir / "skills" / "new-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: New Skill\ndescription: Imported skill\nversion: 1.0.0\n---\nBody", encoding="utf-8"
    )
    repo = _MemorySkillRepo()
    monkeypatch.setattr(import_file_skills_to_library, "build_storage_container", lambda: SimpleNamespace(skill_repo=lambda: repo))

    import_file_skills_to_library.import_skills("owner-1", library_dir)

    assert repo.saved[0].source == {"kind": "file_import"}
    assert repo.packages[0].source == {"kind": "file_import"}


def test_import_file_skill_requires_description_frontmatter(monkeypatch: pytest.MonkeyPatch, tmp_path):
    library_dir = tmp_path / "library"
    skill_dir = library_dir / "skills" / "new-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: New Skill\n---\nBody", encoding="utf-8")
    repo = _MemorySkillRepo()
    monkeypatch.setattr(import_file_skills_to_library, "build_storage_container", lambda: SimpleNamespace(skill_repo=lambda: repo))

    with pytest.raises(ValueError, match="SKILL.md frontmatter must include description"):
        import_file_skills_to_library.import_skills("owner-1", library_dir)

    assert repo.saved == []


def test_import_file_skill_requires_version_frontmatter(monkeypatch: pytest.MonkeyPatch, tmp_path):
    library_dir = tmp_path / "library"
    skill_dir = library_dir / "skills" / "new-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: New Skill\ndescription: New\n---\nBody", encoding="utf-8")
    repo = _MemorySkillRepo()
    monkeypatch.setattr(import_file_skills_to_library, "build_storage_container", lambda: SimpleNamespace(skill_repo=lambda: repo))

    with pytest.raises(ValueError, match="SKILL.md frontmatter must include version"):
        import_file_skills_to_library.import_skills("owner-1", library_dir)

    assert repo.saved == []


def test_import_file_skill_has_no_default_package_version() -> None:
    source = inspect.getsource(import_file_skills_to_library)

    assert "INITIAL_SKILL_PACKAGE_VERSION" not in source
    assert 'return "0.1.0"' not in source


def test_import_file_skill_rejects_adjacent_file_path_collision(monkeypatch: pytest.MonkeyPatch, tmp_path):
    library_dir = tmp_path / "library"
    skill_dir = library_dir / "skills" / "new-skill"
    refs_dir = skill_dir / "references"
    refs_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: New Skill\ndescription: New\nversion: 1.0.0\n---\nBody", encoding="utf-8")
    (refs_dir / "a.md").write_text("Windows-shaped key.", encoding="utf-8")
    (refs_dir / "b.md").write_text("POSIX-shaped key.", encoding="utf-8")
    repo = _MemorySkillRepo()
    original_relative_to = Path.relative_to

    def colliding_relative_to(self: Path, *other: str | PathLike[str]) -> PureWindowsPath | PurePosixPath:
        if self.name == "a.md":
            return PureWindowsPath("references", "query.md")
        if self.name == "b.md":
            return PurePosixPath("references/query.md")
        relative_path = original_relative_to(self, *other)
        return PurePosixPath(*relative_path.parts)

    monkeypatch.setattr(Path, "relative_to", colliding_relative_to)
    monkeypatch.setattr(import_file_skills_to_library, "build_storage_container", lambda: SimpleNamespace(skill_repo=lambda: repo))

    with pytest.raises(ValueError, match="File Skill files contain duplicate path after normalization: references/query.md"):
        import_file_skills_to_library.import_skills("owner-1", library_dir)

    assert repo.saved == []
