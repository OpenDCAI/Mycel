from datetime import UTC, datetime

from config.skill_package import build_skill_package, build_skill_package_hash, build_skill_package_manifest


def test_build_skill_package_uses_content_hash_as_identity() -> None:
    created_at = datetime(2026, 4, 26, tzinfo=UTC)
    skill_md = "---\nname: Query Helper\n---\nUse exact terms."
    files = {"references/query.md": "Prefer precise queries."}

    package = build_skill_package(
        owner_user_id="owner-1",
        skill_id="skill-1",
        version="1.0.0",
        skill_md=skill_md,
        files=files,
        source={"kind": "test"},
        created_at=created_at,
    )

    expected_hash = build_skill_package_hash(skill_md, files)
    assert package.id == expected_hash.removeprefix("sha256:")
    assert package.hash == expected_hash
    assert package.manifest == build_skill_package_manifest(skill_md, files)
    assert package.owner_user_id == "owner-1"
    assert package.skill_id == "skill-1"
    assert package.version == "1.0.0"
    assert package.skill_md == skill_md
    assert package.files == files
    assert package.source == {"kind": "test"}
    assert package.created_at == created_at
