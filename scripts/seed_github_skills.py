"""Batch-upload skills from cloned GitHub repos to the Mycel Hub."""

from pathlib import Path

import httpx

from config.skill_document import parse_skill_document
from config.skill_files import normalize_skill_file_entries

HUB_URL = "http://localhost:8090"

# Publisher mapping: repo_key -> (user_id, username, display_name)
PUBLISHERS = {
    "anthropics": ("anthropics", "anthropics", "Anthropic (Official)"),
    "alirezarezvani": ("alirezarezvani", "alirezarezvani", "Alireza Rezvani"),
    "jezweb": ("jezweb", "jezweb", "JezWeb"),
}

# Repos to process: (repo_key, local_path, skill_root_dirs)
REPOS = [
    ("anthropics", Path("/tmp/skill-repos/anthropics-skills"), [Path("skills")]),
    ("alirezarezvani", Path("/tmp/skill-repos/alirezarezvani-skills"), None),  # scan all
    ("jezweb", Path("/tmp/skill-repos/jezweb-skills"), None),  # scan all
]

# Skip directories that are not skills
SKIP_DIRS = {
    ".git",
    ".github",
    "node_modules",
    "__pycache__",
    "docs",
    "doc",
    "template",
    "spec",
    "eval-workspace",
    "custom-gpt",
    "commands",
    "tools",
    ".vscode",
}


def register_publisher(user_id: str, username: str, display_name: str) -> None:
    httpx.post(
        f"{HUB_URL}/api/v1/publishers/register",
        json={
            "user_id": user_id,
            "username": username,
            "display_name": display_name,
        },
        timeout=10.0,
    ).raise_for_status()


def register_all_publishers() -> None:
    for _key, (uid, uname, dname) in PUBLISHERS.items():
        register_publisher(uid, uname, dname)
        print(f"Publisher registered: {uname}")


def parse_skill_md(skill_md: Path) -> dict | None:
    """Parse a SKILL.md into name/description/tags."""
    content = skill_md.read_text(encoding="utf-8")
    if len(content.strip()) < 50:
        return None

    document = parse_skill_document(content, label="SKILL.md", require_description=True, require_version=True)
    name = document.name
    description = document.description
    version = document.version
    if version is None:
        raise RuntimeError("SKILL.md version was not parsed")
    tags = []
    meta = document.frontmatter.get("metadata", {})
    if isinstance(meta, dict):
        for key in ("domain", "role", "category"):
            if meta.get(key):
                tags.append(str(meta[key]))
        triggers = meta.get("triggers", "")
        if isinstance(triggers, str):
            tags.extend([t.strip() for t in triggers.split(",")[:5] if t.strip()])

    return {
        "name": name,
        "description": description,
        "version": version,
        "tags": sorted({t for t in tags if t})[:10],
        "content": content,
    }


def _read_adjacent_files(skill_dir: Path) -> dict[str, str]:
    file_entries: list[tuple[str, str]] = []
    for path in sorted(skill_dir.rglob("*")):
        if not path.is_file() or path.name == "SKILL.md":
            continue
        try:
            file_entries.append((path.relative_to(skill_dir).as_posix(), path.read_text(encoding="utf-8")))
        except UnicodeDecodeError as exc:
            raise RuntimeError(f"Skill adjacent file could not be read: {path}") from exc
    return normalize_skill_file_entries(file_entries, context="Seed Skill files")


def read_skill_package(skill_dir: Path) -> dict | None:
    parsed = parse_skill_md(skill_dir / "SKILL.md")
    if parsed is None:
        return None
    parsed["files"] = _read_adjacent_files(skill_dir)
    return parsed


def find_skill_dirs(repo_root: Path, skill_roots: list[Path] | None) -> list[Path]:
    """Find all directories containing SKILL.md."""
    results = []
    if skill_roots:
        for root in skill_roots:
            full = repo_root / root
            if not full.exists():
                continue
            for skill_md in full.rglob("SKILL.md"):
                results.append(skill_md.parent)
    else:
        for skill_md in repo_root.rglob("SKILL.md"):
            # Skip if any parent dir is in SKIP_DIRS
            parts = skill_md.relative_to(repo_root).parts
            if any(p in SKIP_DIRS for p in parts):
                continue
            results.append(skill_md.parent)
    return sorted(set(results))


def build_skill_slug(repo_root: Path, skill_dir: Path) -> str:
    rel = skill_dir.relative_to(repo_root)
    parts = [part for part in rel.parts if part not in SKIP_DIRS]
    return "--".join(parts) if len(parts) > 1 else skill_dir.name


def build_skill_payload(
    *,
    slug: str,
    package: dict,
    publisher_user_id: str,
    publisher_username: str,
) -> dict:
    return {
        "slug": slug,
        "type": "skill",
        "name": package["name"],
        "description": package["description"],
        "version": package["version"],
        "release_notes": "Initial release",
        "tags": package["tags"],
        "visibility": "public",
        "snapshot": {
            "meta": {"name": package["name"], "desc": package["description"]},
            "content": package["content"],
            "files": package["files"],
        },
        "parent_item_id": None,
        "parent_version": None,
        "publisher_user_id": publisher_user_id,
        "publisher_username": publisher_username,
    }


def read_existing_hub_slugs() -> set[tuple[str, str]]:
    response = httpx.get(f"{HUB_URL}/api/v1/items?page_size=2000", timeout=30.0)
    response.raise_for_status()
    existing = response.json()
    return {(item["publisher_username"], item["slug"]) for item in existing.get("items", [])}


def upload(payload: dict) -> bool:
    import time

    for attempt in range(3):
        try:
            resp = httpx.post(f"{HUB_URL}/api/v1/publish", json=payload, timeout=30.0)
            resp.raise_for_status()
            return True
        except (httpx.ConnectError, httpx.RemoteProtocolError, httpx.TimeoutException) as e:
            if attempt < 2:
                time.sleep(1 + attempt)
                continue
            print(f"  FAIL: {e}")
            return False
        except httpx.HTTPStatusError as e:
            print(f"  FAIL: {e}")
            return False
    return False


def publish_skill_package(
    *,
    slug: str,
    package: dict,
    publisher_user_id: str,
    publisher_username: str,
) -> bool:
    payload = build_skill_payload(
        slug=slug,
        package=package,
        publisher_user_id=publisher_user_id,
        publisher_username=publisher_username,
    )
    return upload(payload)


def main():
    register_all_publishers()

    # Check existing items to avoid duplicates
    existing_slugs = read_existing_hub_slugs()
    print(f"\nExisting items in Hub: {len(existing_slugs)}")

    total_ok = 0
    total_fail = 0
    total_skip = 0

    for repo_key, repo_root, skill_roots in REPOS:
        if not repo_root.exists():
            print(f"\nSKIP repo: {repo_root} (not found)")
            continue

        uid, uname, dname = PUBLISHERS[repo_key]
        skill_dirs = find_skill_dirs(repo_root, skill_roots)
        print(f"\n=== {repo_key} ({len(skill_dirs)} skills found) ===")

        for skill_dir in skill_dirs:
            # Hub item slug is marketplace address only; Library Skill id is generated downstream.
            slug = build_skill_slug(repo_root, skill_dir)

            # Skip if already exists
            if (uname, slug) in existing_slugs:
                total_skip += 1
                continue

            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                total_skip += 1
                continue

            package = read_skill_package(skill_dir)
            if not package:
                print(f"  SKIP: {slug} (too short)")
                total_skip += 1
                continue

            print(f"  Upload: {slug} ...", end=" ")
            if publish_skill_package(
                slug=slug,
                package=package,
                publisher_user_id=uid,
                publisher_username=uname,
            ):
                print("OK")
                total_ok += 1
            else:
                total_fail += 1

    print(f"\nDone: {total_ok} uploaded, {total_fail} failed, {total_skip} skipped")


if __name__ == "__main__":
    main()
