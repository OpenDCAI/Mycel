"""Batch-upload local SKILL.md files to the Mycel Hub."""

import json
import sys
from pathlib import Path

import httpx

HUB_URL = "http://localhost:8090"
PUBLISHER_USER_ID = "system"
PUBLISHER_USERNAME = "mycel-official"

# Skills to SKIP (project-specific, not general purpose)
SKIP = {
    "bench", "sks", "sksadd", "sksgnew", "sksgrm", "sksls",
    "sksoff", "skson", "sksrm", "skssearch", "wtpr", "wtrm",
    "wtls", "wtsync", "wtrebaseall", "wtnew", "invit",
    "test_leon", "spec", "the-fool",
}


def parse_skill(skill_dir: Path) -> dict | None:
    """Parse a SKILL.md into Hub publish payload."""
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        # Try any .md file
        mds = list(skill_dir.glob("*.md"))
        if not mds:
            return None
        skill_md = mds[0]

    content = skill_md.read_text(encoding="utf-8")

    # Parse YAML frontmatter
    name = skill_dir.name
    description = ""
    tags = []
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            import yaml
            try:
                fm = yaml.safe_load(parts[1])
                if fm:
                    name = fm.get("name", name)
                    description = fm.get("description", "")
                    meta = fm.get("metadata", {})
                    if meta:
                        if meta.get("domain"):
                            tags.append(meta["domain"])
                        if meta.get("role"):
                            tags.append(meta["role"])
                        triggers = meta.get("triggers", "")
                        if isinstance(triggers, str):
                            tags.extend([t.strip() for t in triggers.split(",")[:5]])
            except Exception:
                pass

    if not description:
        # Extract first paragraph after heading
        lines = content.split("\n")
        for line in lines:
            if line.strip() and not line.startswith("#") and not line.startswith("---"):
                description = line.strip()[:200]
                break

    return {
        "slug": skill_dir.name,
        "type": "skill",
        "name": name,
        "description": description,
        "version": "1.0.0",
        "release_notes": "Initial release",
        "tags": list(set(tags))[:10],
        "visibility": "public",
        "snapshot": {
            "meta": {"name": name, "desc": description},
            "content": content,
        },
        "parent_item_id": None,
        "parent_version": None,
        "publisher_user_id": PUBLISHER_USER_ID,
        "publisher_username": PUBLISHER_USERNAME,
    }


def upload(payload: dict) -> bool:
    """Upload a skill to the Hub."""
    try:
        resp = httpx.post(f"{HUB_URL}/api/v1/publish", json=payload, timeout=15.0)
        resp.raise_for_status()
        return True
    except Exception as e:
        print(f"  FAIL: {e}")
        return False


def main():
    sources = [
        Path("/Users/apple/worktrees/Mycel--feat-marketplace/.claude/skills"),
        Path("/Users/apple/.claude/plugins/cache/fullstack-dev-skills/fullstack-dev-skills/0.4.7/skills"),
    ]

    # Register publisher first
    try:
        httpx.post(f"{HUB_URL}/api/v1/publishers/register", json={
            "user_id": PUBLISHER_USER_ID,
            "username": PUBLISHER_USERNAME,
            "display_name": "Mycel Official",
            "bio": "Official curated skills for the Mycel marketplace",
        }, timeout=10.0).raise_for_status()
        print("Publisher registered: mycel-official")
    except Exception as e:
        print(f"Publisher registration: {e}")

    ok = 0
    fail = 0
    skip = 0

    for source in sources:
        if not source.exists():
            print(f"SKIP source: {source}")
            continue
        print(f"\n=== {source} ===")
        for skill_dir in sorted(source.iterdir()):
            if not skill_dir.is_dir():
                continue
            if skill_dir.name in SKIP:
                print(f"  SKIP: {skill_dir.name} (project-specific)")
                skip += 1
                continue

            payload = parse_skill(skill_dir)
            if not payload:
                print(f"  SKIP: {skill_dir.name} (no SKILL.md)")
                skip += 1
                continue

            print(f"  Upload: {payload['name']} ...", end=" ")
            if upload(payload):
                print("OK")
                ok += 1
            else:
                fail += 1

    print(f"\nDone: {ok} uploaded, {fail} failed, {skip} skipped")


if __name__ == "__main__":
    main()
