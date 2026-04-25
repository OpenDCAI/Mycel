from __future__ import annotations

import inspect
from pathlib import Path, PureWindowsPath
from types import SimpleNamespace

import pytest
import yaml

from scripts import seed_github_skills


def _write_skill(skill_dir: Path, content: str) -> None:
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")


def test_seed_skill_package_includes_adjacent_files(tmp_path: Path) -> None:
    skill_dir = tmp_path / "repo" / "skills" / "api-design"
    _write_skill(
        skill_dir,
        "---\nname: API Design\ndescription: Design APIs\nmetadata:\n  domain: backend\n---\nUse REST carefully.",
    )
    (skill_dir / "references").mkdir()
    (skill_dir / "references" / "routing.md").write_text("Prefer explicit routes.", encoding="utf-8")

    package = seed_github_skills.read_skill_package(skill_dir)

    assert package == {
        "name": "API Design",
        "description": "Design APIs",
        "tags": ["backend"],
        "content": "---\nname: API Design\ndescription: Design APIs\nmetadata:\n  domain: backend\n---\nUse REST carefully.",
        "files": {"references/routing.md": "Prefer explicit routes."},
    }


def test_seed_skill_package_normalizes_adjacent_file_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    skill_dir = tmp_path / "repo" / "skills" / "api-design"
    _write_skill(skill_dir, "---\nname: API Design\ndescription: Design APIs\n---\nUse REST carefully.")
    refs_dir = skill_dir / "references"
    refs_dir.mkdir()
    (refs_dir / "routing.md").write_text("Prefer explicit routes.", encoding="utf-8")
    original_relative_to = Path.relative_to

    def windows_relative_to(self: Path, *other: str | Path) -> PureWindowsPath:
        return PureWindowsPath(*original_relative_to(self, *other).parts)

    monkeypatch.setattr(Path, "relative_to", windows_relative_to)

    package = seed_github_skills.read_skill_package(skill_dir)

    assert package is not None
    assert package["files"] == {"references/routing.md": "Prefer explicit routes."}


def test_seed_skill_parse_fails_loudly_on_invalid_frontmatter(tmp_path: Path) -> None:
    skill_dir = tmp_path / "repo" / "skills" / "broken"
    _write_skill(skill_dir, "---\nname: [broken\n---\nBody long enough to avoid the tiny file skip path.")

    with pytest.raises(yaml.YAMLError):
        seed_github_skills.read_skill_package(skill_dir)


def test_seed_skill_parse_rejects_non_text_frontmatter_name(tmp_path: Path) -> None:
    skill_dir = tmp_path / "repo" / "skills" / "broken"
    _write_skill(skill_dir, "---\nname: 123\ndescription: Broken\n---\nBody long enough to parse.")

    with pytest.raises(ValueError, match="SKILL.md frontmatter name must be a string"):
        seed_github_skills.read_skill_package(skill_dir)


def test_seed_skill_parse_rejects_unreadable_skill_md(tmp_path: Path) -> None:
    skill_dir = tmp_path / "repo" / "skills" / "broken"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_bytes(b"\xff\xfe\xfa")

    with pytest.raises(UnicodeDecodeError):
        seed_github_skills.read_skill_package(skill_dir)


def test_seed_skill_payload_publishes_snapshot_files(tmp_path: Path) -> None:
    skill_dir = tmp_path / "repo" / "skills" / "api-design"
    _write_skill(skill_dir, "---\nname: API Design\ndescription: Design APIs\n---\nUse REST carefully.")
    (skill_dir / "references").mkdir()
    (skill_dir / "references" / "routing.md").write_text("Prefer explicit routes.", encoding="utf-8")
    package = seed_github_skills.read_skill_package(skill_dir)
    assert package is not None

    payload = seed_github_skills.build_skill_payload(
        slug="skills--api-design",
        package=package,
        publisher_user_id="publisher-1",
        publisher_username="publisher",
    )

    assert payload["snapshot"]["content"] == package["content"]
    assert payload["snapshot"]["files"] == {"references/routing.md": "Prefer explicit routes."}


def test_seed_skill_slug_is_hub_item_path_not_library_identity(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    skill_dir = repo_root / "skills" / "backend" / "api-design"
    skill_dir.mkdir(parents=True)

    slug = seed_github_skills.build_skill_slug(repo_root, skill_dir)

    assert slug == "skills--backend--api-design"


def test_seed_existing_hub_slugs_require_successful_response(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, str] = {}

    def fake_get(url: str, timeout: float):
        seen["url"] = url
        seen["timeout"] = str(timeout)
        return SimpleNamespace(
            raise_for_status=lambda: seen.setdefault("raised", "yes"),
            json=lambda: {
                "items": [
                    {"publisher_username": "anthropics", "slug": "skills--planner"},
                    {"publisher_username": "mycel", "slug": "skills--reviewer"},
                ]
            },
        )

    monkeypatch.setattr(seed_github_skills.httpx, "get", fake_get)

    slugs = seed_github_skills.read_existing_hub_slugs()

    assert seen == {"url": "http://localhost:8090/api/v1/items?page_size=2000", "timeout": "30.0", "raised": "yes"}
    assert slugs == {("anthropics", "skills--planner"), ("mycel", "skills--reviewer")}


def test_seed_publish_skill_package_uses_package_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, dict] = {}

    def fake_upload(payload: dict) -> bool:
        seen["payload"] = payload
        return True

    monkeypatch.setattr(seed_github_skills, "upload", fake_upload)

    ok = seed_github_skills.publish_skill_package(
        slug="skills--api-design",
        package={
            "name": "API Design",
            "description": "Design APIs",
            "tags": ["backend"],
            "content": "---\nname: API Design\n---\nUse REST carefully.",
            "files": {"references/routing.md": "Prefer explicit routes."},
        },
        publisher_user_id="publisher-1",
        publisher_username="publisher",
    )

    assert ok is True
    assert seen["payload"]["snapshot"]["files"] == {"references/routing.md": "Prefer explicit routes."}
    assert seen["payload"]["publisher_username"] == "publisher"


def test_seed_skill_parser_does_not_swallow_parse_errors() -> None:
    source = inspect.getsource(seed_github_skills.parse_skill_md)

    assert "except Exception" not in source
    assert "pass" not in source


def test_seed_script_does_not_catch_broad_exceptions() -> None:
    source = inspect.getsource(seed_github_skills)

    assert "except Exception" not in source
