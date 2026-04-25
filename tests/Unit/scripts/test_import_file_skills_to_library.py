from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from config.agent_config_types import Skill
from scripts import import_file_skills_to_library


class _MemorySkillRepo:
    def __init__(self, existing: Skill | None = None) -> None:
        self.existing = existing
        self.saved: list[Skill] = []

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


def test_import_file_skill_rejects_name_drift_for_existing_skill_id(monkeypatch: pytest.MonkeyPatch, tmp_path):
    library_dir = tmp_path / "library"
    skill_dir = library_dir / "skills" / "same-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: Renamed Skill\n---\nBody", encoding="utf-8")
    repo = _MemorySkillRepo(
        Skill(
            id="same-skill",
            owner_user_id="owner-1",
            name="Original Skill",
            content="---\nname: Original Skill\n---\nBody",
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
    (skill_dir / "SKILL.md").write_text("---\nname: Shared Skill\n---\nBody", encoding="utf-8")
    repo = _MemorySkillRepo(
        Skill(
            id="original-skill",
            owner_user_id="owner-1",
            name="Shared Skill",
            content="---\nname: Shared Skill\n---\nBody",
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
    (skill_dir / "SKILL.md").write_text("---\nname: New Skill\n---\nBody", encoding="utf-8")
    (skill_dir / "broken.bin").write_bytes(b"\xff\xfe\xfa")
    repo = _MemorySkillRepo()
    monkeypatch.setattr(import_file_skills_to_library, "build_storage_container", lambda: SimpleNamespace(skill_repo=lambda: repo))

    with pytest.raises(RuntimeError, match="Skill adjacent file could not be read"):
        import_file_skills_to_library.import_skills("owner-1", library_dir)

    assert repo.saved == []
