"""Batch-upload skills from cloned GitHub repos to the Mycel Hub."""

import sys
from pathlib import Path

import httpx
import yaml

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
    ".git", ".github", "node_modules", "__pycache__", "docs", "doc",
    "template", "spec", "eval-workspace", "custom-gpt", "commands",
    "tools", ".vscode",
}


def register_publisher(user_id: str, username: str, display_name: str) -> None:
    try:
        httpx.post(f"{HUB_URL}/api/v1/publishers/register", json={
            "user_id": user_id,
            "username": username,
            "display_name": display_name,
        }, timeout=10.0).raise_for_status()
    except Exception as e:
        print(f"  Publisher {username}: {e}")


def parse_skill_md(skill_md: Path) -> dict | None:
    """Parse a SKILL.md into name/description/tags."""
    content = skill_md.read_text(encoding="utf-8", errors="replace")
    if len(content.strip()) < 50:
        return None

    name = skill_md.parent.name
    description = ""
    tags = []

    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            try:
                fm = yaml.safe_load(parts[1])
                if fm and isinstance(fm, dict):
                    name = fm.get("name", name)
                    description = fm.get("description", "")
                    meta = fm.get("metadata", {})
                    if isinstance(meta, dict):
                        for key in ("domain", "role", "category"):
                            if meta.get(key):
                                tags.append(str(meta[key]))
                        triggers = meta.get("triggers", "")
                        if isinstance(triggers, str):
                            tags.extend([t.strip() for t in triggers.split(",")[:5] if t.strip()])
            except Exception:
                pass

    if not description:
        for line in content.split("\n"):
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and not stripped.startswith("---"):
                description = stripped[:200]
                break

    return {
        "name": name,
        "description": description,
        "tags": list(set(t for t in tags if t))[:10],
        "content": content,
    }


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


def upload(payload: dict) -> bool:
    import time
    for attempt in range(3):
        try:
            resp = httpx.post(f"{HUB_URL}/api/v1/publish", json=payload, timeout=30.0)
            resp.raise_for_status()
            return True
        except Exception as e:
            if attempt < 2 and ("Connection reset" in str(e) or "timed out" in str(e)):
                time.sleep(1 + attempt)
                continue
            print(f"  FAIL: {e}")
            return False
    return False


def main():
    # Register all publishers
    for key, (uid, uname, dname) in PUBLISHERS.items():
        register_publisher(uid, uname, dname)
        print(f"Publisher registered: {uname}")

    # Check existing items to avoid duplicates
    try:
        existing = httpx.get(f"{HUB_URL}/api/v1/items?page_size=2000", timeout=30.0).json()
        existing_slugs = {(item["publisher_username"], item["slug"]) for item in existing.get("items", [])}
        print(f"\nExisting items in Hub: {len(existing_slugs)}")
    except Exception:
        existing_slugs = set()

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
            # Use relative path as slug to avoid collisions in nested repos
            rel = skill_dir.relative_to(repo_root)
            parts = [p for p in rel.parts if p not in SKIP_DIRS]
            slug = "--".join(parts) if len(parts) > 1 else skill_dir.name

            # Skip if already exists
            if (uname, slug) in existing_slugs:
                total_skip += 1
                continue

            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                total_skip += 1
                continue

            parsed = parse_skill_md(skill_md)
            if not parsed:
                print(f"  SKIP: {slug} (too short)")
                total_skip += 1
                continue

            payload = {
                "slug": slug,
                "type": "skill",
                "name": parsed["name"],
                "description": parsed["description"],
                "version": "1.0.0",
                "release_notes": "Initial release",
                "tags": parsed["tags"],
                "visibility": "public",
                "snapshot": {
                    "meta": {"name": parsed["name"], "desc": parsed["description"]},
                    "content": parsed["content"],
                },
                "parent_item_id": None,
                "parent_version": None,
                "publisher_user_id": uid,
                "publisher_username": uname,
            }

            print(f"  Upload: {slug} ...", end=" ")
            if upload(payload):
                print("OK")
                total_ok += 1
            else:
                total_fail += 1

    print(f"\nDone: {total_ok} uploaded, {total_fail} failed, {total_skip} skipped")


if __name__ == "__main__":
    main()
