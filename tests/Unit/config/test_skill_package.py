import inspect
from datetime import UTC, datetime

import pytest

from config.agent_config_types import SkillPackage
from config.skill_package import build_skill_package, build_skill_package_hash, build_skill_package_id, build_skill_package_manifest


def test_build_skill_package_separates_row_identity_from_content_hash() -> None:
    created_at = datetime(2026, 4, 26, tzinfo=UTC)
    skill_md = "---\nname: Query Helper\ndescription: Build precise queries\nversion: 1.2.3\n---\nUse exact terms."
    files = {"references/query.md": "Prefer precise queries."}

    package = build_skill_package(
        owner_user_id="owner-1",
        skill_id="skill-1",
        skill_md=skill_md,
        files=files,
        source={"kind": "test"},
        created_at=created_at,
    )

    expected_hash = build_skill_package_hash(skill_md, files)
    assert package.id == build_skill_package_id("owner-1", "skill-1", expected_hash)
    assert package.id != expected_hash.removeprefix("sha256:")
    assert package.hash == expected_hash
    assert package.manifest == build_skill_package_manifest(skill_md, files)
    assert package.owner_user_id == "owner-1"
    assert package.skill_id == "skill-1"
    assert package.version == "1.2.3"
    assert package.skill_md == skill_md
    assert package.files == files
    assert package.source == {"kind": "test"}
    assert package.created_at == created_at


def test_build_skill_package_row_identity_is_scoped_to_owner_and_skill() -> None:
    created_at = datetime(2026, 4, 26, tzinfo=UTC)
    skill_md = "---\nname: Query Helper\ndescription: Build precise queries\nversion: 1.2.3\n---\nUse exact terms."

    owner_one = build_skill_package(
        owner_user_id="owner-1",
        skill_id="skill-1",
        skill_md=skill_md,
        files={},
        source={},
        created_at=created_at,
    )
    owner_two = build_skill_package(
        owner_user_id="owner-2",
        skill_id="skill-1",
        skill_md=skill_md,
        files={},
        source={},
        created_at=created_at,
    )
    skill_two = build_skill_package(
        owner_user_id="owner-1",
        skill_id="skill-2",
        skill_md=skill_md,
        files={},
        source={},
        created_at=created_at,
    )

    assert owner_one.hash == owner_two.hash == skill_two.hash
    assert len({owner_one.id, owner_two.id, skill_two.id}) == 3


def test_build_skill_package_has_no_external_version_argument() -> None:
    assert "version" not in inspect.signature(build_skill_package).parameters


def test_skill_package_requires_skill_md_version_frontmatter() -> None:
    with pytest.raises(ValueError, match="skill_package.skill_md frontmatter must include version"):
        SkillPackage(
            id="package-1",
            owner_user_id="owner-1",
            skill_id="skill-1",
            version="1.0.0",
            hash="sha256:package-1",
            skill_md="---\nname: Query Helper\ndescription: Build precise queries\n---\nUse exact terms.",
            created_at=datetime(2026, 4, 26, tzinfo=UTC),
        )


def test_skill_package_version_matches_skill_md_frontmatter() -> None:
    with pytest.raises(ValueError, match="skill_package.version must match SKILL.md frontmatter version"):
        SkillPackage(
            id="package-1",
            owner_user_id="owner-1",
            skill_id="skill-1",
            version="2.0.0",
            hash="sha256:package-1",
            skill_md=("---\nname: Query Helper\ndescription: Build precise queries\nversion: 1.0.0\n---\nUse exact terms."),
            created_at=datetime(2026, 4, 26, tzinfo=UTC),
        )
