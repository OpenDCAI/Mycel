"""HTTP client for Mycel Hub marketplace API."""
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

import httpx
from fastapi import HTTPException

from backend.web.core.paths import members_dir
from config.loader import AgentLoader

logger = logging.getLogger(__name__)

HUB_URL = os.environ.get("MYCEL_HUB_URL", "http://localhost:8080")

_hub_client = httpx.Client(timeout=30.0)


def _hub_api(method: str, path: str, **kwargs: Any) -> dict:
    """Call Hub API."""
    url = f"{HUB_URL}/api/v1{path}"
    try:
        resp = _hub_client.request(method, url, **kwargs)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        if status == 404:
            raise HTTPException(status_code=404, detail="Marketplace item not found")
        elif status == 409:
            raise HTTPException(status_code=409, detail="Item already exists with this version")
        else:
            raise HTTPException(status_code=502, detail=f"Hub API error: {status}")
    except (httpx.ConnectError, httpx.TimeoutException):
        raise HTTPException(status_code=503, detail="Marketplace Hub unavailable")


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _serialize_member_snapshot(member_id: str) -> dict:
    """Serialize a local member into a snapshot dict for Hub."""
    member_dir = members_dir() / member_id

    # Read raw files for faithful snapshot
    agent_md = (member_dir / "agent.md").read_text(encoding="utf-8")

    rules = []
    rules_dir = member_dir / "rules"
    if rules_dir.is_dir():
        for md in sorted(rules_dir.glob("*.md")):
            rules.append({"name": md.stem, "content": md.read_text(encoding="utf-8")})

    # Sub-agents
    agents = []
    agents_dir = member_dir / "agents"
    if agents_dir.is_dir():
        for md in sorted(agents_dir.glob("*.md")):
            agents.append({"name": md.stem, "content": md.read_text(encoding="utf-8")})

    # Skills
    skills = []
    skills_dir = member_dir / "skills"
    if skills_dir.is_dir():
        for skill_dir in sorted(skills_dir.iterdir()):
            if skill_dir.is_dir():
                skill_md = skill_dir / "SKILL.md"
                if skill_md.exists():
                    meta = _read_json(skill_dir / "meta.json")
                    skills.append({
                        "name": skill_dir.name,
                        "content": skill_md.read_text(encoding="utf-8"),
                        "meta": meta,
                    })

    # MCP
    mcp = _read_json(member_dir / ".mcp.json")

    # Runtime
    runtime = _read_json(member_dir / "runtime.json")

    return {
        "agent_md": agent_md,
        "rules": rules,
        "agents": agents,
        "skills": skills,
        "mcp": mcp,
        "runtime": runtime,
        "meta": _read_json(member_dir / "meta.json"),
    }


def publish(
    member_id: str,
    type_: str,
    bump_type: str,
    release_notes: str,
    tags: list[str],
    visibility: str,
    publisher_user_id: str,
    publisher_username: str,
) -> dict:
    """Publish a local member to the Hub."""
    member_dir = members_dir() / member_id
    meta = _read_json(member_dir / "meta.json")

    # Calculate new version
    current_version = meta.get("version", "0.1.0")
    parts = current_version.split(".")
    major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
    if bump_type == "major":
        major, minor, patch = major + 1, 0, 0
    elif bump_type == "minor":
        minor, patch = minor + 1, 0
    else:
        patch += 1
    new_version = f"{major}.{minor}.{patch}"

    # Serialize snapshot
    snapshot = _serialize_member_snapshot(member_id)

    # Get slug from agent name
    loader = AgentLoader()
    bundle = loader.load_bundle(member_dir)
    slug = bundle.agent.name.lower().replace(" ", "-")

    # Check for fork/parent relationship
    source = meta.get("source", {})
    parent_item_id = source.get("marketplace_item_id")
    parent_version = source.get("installed_version")

    # Call Hub API
    result = _hub_api("POST", "/publish", json={
        "slug": slug,
        "type": type_,
        "name": bundle.agent.name,
        "description": bundle.agent.description,
        "version": new_version,
        "release_notes": release_notes,
        "tags": tags,
        "visibility": visibility,
        "snapshot": snapshot,
        "parent_item_id": parent_item_id,
        "parent_version": parent_version,
        "publisher_user_id": publisher_user_id,
        "publisher_username": publisher_username,
    })

    # Update local meta.json
    meta["version"] = new_version
    meta["status"] = "active"
    meta["updated_at"] = int(time.time() * 1000)
    if "source" not in meta:
        meta["source"] = {}
    meta["source"]["marketplace_item_id"] = result.get("item_id")
    meta["source"]["installed_version"] = new_version
    meta["source"]["installed_at"] = int(time.time() * 1000)
    meta["source"]["modified"] = False
    _write_json(member_dir / "meta.json", meta)

    return result


def download(item_id: str, owner_user_id: str = "system") -> dict:
    """Download a marketplace item to local library."""
    result = _hub_api("POST", f"/items/{item_id}/download")
    snapshot = result["snapshot"]
    item = result["item"]
    installed_version = result["version"]
    item_type = item.get("type", "skill")

    from backend.web.services.library_service import LIBRARY_DIR
    now = int(time.time() * 1000)

    if item_type == "skill":
        slug = item.get("slug", item["name"].lower().replace(" ", "-"))
        skill_dir = (LIBRARY_DIR / "skills" / slug).resolve()
        if not skill_dir.is_relative_to((LIBRARY_DIR / "skills").resolve()):
            raise ValueError(f"Invalid slug: {slug}")
        skill_dir.mkdir(parents=True, exist_ok=True)

        # Write SKILL.md
        content = snapshot.get("content", "")
        (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")

        # Write meta.json with marketplace source info
        meta = snapshot.get("meta", {})
        meta_data = {
            "name": meta.get("name", item["name"]),
            "desc": meta.get("desc", item.get("description", "")),
            "category": ", ".join(item.get("tags", [])),
            "created_at": now,
            "updated_at": now,
            "source": {
                "marketplace_item_id": item_id,
                "installed_version": installed_version,
                "installed_at": now,
                "publisher": item.get("publisher_username", ""),
            },
        }
        _write_json(skill_dir / "meta.json", meta_data)
        logger.info("Downloaded skill %s to library", slug)
        return {"resource_id": slug, "type": "skill", "version": installed_version}

    elif item_type == "agent":
        slug = item.get("slug", item["name"].lower().replace(" ", "-"))
        agent_dir = (LIBRARY_DIR / "agents").resolve()
        if not (agent_dir / slug).resolve().is_relative_to(agent_dir):
            raise ValueError(f"Invalid slug: {slug}")
        agent_dir.mkdir(parents=True, exist_ok=True)

        content = snapshot.get("content", "")
        (agent_dir / f"{slug}.md").write_text(content, encoding="utf-8")

        meta_data = {
            "name": item["name"],
            "desc": item.get("description", ""),
            "created_at": now,
            "updated_at": now,
            "source": {
                "marketplace_item_id": item_id,
                "installed_version": installed_version,
                "installed_at": now,
                "publisher": item.get("publisher_username", ""),
            },
        }
        _write_json(agent_dir / f"{slug}.json", meta_data)
        logger.info("Downloaded agent %s to library", slug)
        return {"resource_id": slug, "type": "agent", "version": installed_version}

    elif item_type == "member":
        # Members still get installed as full members
        from backend.web.services.member_service import install_from_snapshot
        member_id = install_from_snapshot(
            snapshot=snapshot,
            name=item["name"],
            description=item.get("description", ""),
            marketplace_item_id=item_id,
            installed_version=installed_version,
            owner_user_id=owner_user_id,
        )
        return {"resource_id": member_id, "type": "member", "version": installed_version}

    else:
        raise ValueError(f"Unsupported item type: {item_type}")


def upgrade(member_id: str, item_id: str, owner_user_id: str) -> dict:
    """Upgrade a locally installed marketplace item."""
    result = _hub_api("POST", f"/items/{item_id}/download")
    snapshot = result["snapshot"]
    installed_version = result["version"]

    from backend.web.services.member_service import install_from_snapshot
    install_from_snapshot(
        snapshot=snapshot,
        name=result["item"]["name"],
        description=result["item"].get("description", ""),
        marketplace_item_id=item_id,
        installed_version=installed_version,
        owner_user_id=owner_user_id,
        existing_member_id=member_id,
    )

    return {"member_id": member_id, "version": installed_version}


def check_updates(items: list[dict]) -> dict:
    """Check for updates for installed marketplace items."""
    return _hub_api("POST", "/check-updates", json={"installed": items})
