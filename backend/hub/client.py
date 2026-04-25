"""HTTP client for Mycel Hub marketplace API."""

import copy
import os
import time
from datetime import UTC, datetime
from typing import Any

import httpx
import yaml
from fastapi import HTTPException

import backend.hub.snapshot_apply as _snapshot_apply
from backend.hub.versioning import BumpType, bump_semver
from config.agent_config_resolver import resolve_agent_config
from config.agent_config_types import Skill, SkillPackage
from config.agent_snapshot import snapshot_from_resolved_config
from config.skill_files import normalize_skill_file_map
from config.skill_package import build_skill_package_hash, build_skill_package_manifest
from storage.utils import generate_skill_id

HUB_URL = os.environ.get("MYCEL_HUB_URL", "https://hub.mycel.nextmind.space")
# @@@hub-agent-user-item-type - Hub still names published Agent users "member";
# Mycel app domain code exposes them as Agent users.
HUB_AGENT_USER_ITEM_TYPE = "member"

_hub_client = httpx.Client(timeout=30.0, trust_env=False)


def _hub_api(method: str, path: str, **kwargs: Any) -> dict:
    """Call Hub API."""
    url = f"{HUB_URL}/api/v1{path}"
    try:
        resp = _hub_client.request(method, url, **kwargs)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        detail = _hub_error_detail(e.response)
        if status == 400:
            raise HTTPException(status_code=400, detail=detail or "Marketplace Hub request rejected")
        if status == 404:
            raise HTTPException(status_code=404, detail="Marketplace item not found")
        if status == 409:
            raise HTTPException(status_code=409, detail="Item already exists with this version")
        raise HTTPException(status_code=502, detail=f"Hub API error: {status}")
    except (httpx.ConnectError, httpx.TimeoutException):
        raise HTTPException(status_code=503, detail="Marketplace Hub unavailable")


def _hub_error_detail(response: httpx.Response) -> str | None:
    try:
        payload = response.json()
    except ValueError:
        return None
    detail = payload.get("detail") if isinstance(payload, dict) else None
    return detail if isinstance(detail, str) and detail else None


def _required_object(value: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _required_text(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a string")
    return value.strip()


def _optional_text(value: Any, *, label: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    return value.strip()


def _skill_metadata_from_content(content: str) -> dict[str, Any]:
    if not content.startswith("---\n"):
        raise ValueError("Skill snapshot must be a SKILL.md document with frontmatter")
    try:
        _, frontmatter, _body = content.split("---", 2)
    except ValueError as exc:
        raise ValueError("Skill snapshot must be a SKILL.md document with frontmatter") from exc
    try:
        metadata = yaml.safe_load(frontmatter) or {}
    except yaml.YAMLError as exc:
        raise ValueError("Skill snapshot frontmatter must be valid YAML") from exc
    if not isinstance(metadata, dict):
        raise ValueError("Skill snapshot frontmatter must include name")
    name = metadata.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Skill snapshot frontmatter must include name")
    metadata["name"] = name.strip()
    return metadata


def _skill_description_from_metadata(metadata: dict[str, Any]) -> str:
    return _optional_text(metadata.get("description"), label="Skill snapshot frontmatter description")


def _skill_files_from_snapshot(snapshot: dict[str, Any]) -> dict[str, str]:
    files = snapshot.get("files", {})
    if files is None:
        return {}
    if not isinstance(files, dict):
        raise ValueError("Skill snapshot files must be an object")
    return normalize_skill_file_map(files, context="Skill snapshot files")


def _hub_source_skill(skills: list[Skill], item_id: str) -> Skill | None:
    for skill in skills:
        if skill.source.get("marketplace_item_id") == item_id:
            return skill
    return None


def list_items(
    *,
    type: str | None = None,
    q: str | None = None,
    sort: str = "downloads",
    page: int = 1,
    page_size: int = 20,
) -> dict:
    params: dict[str, Any] = {
        "sort": sort,
        "page": page,
        "page_size": page_size,
    }
    if type:
        params["type"] = type
    if q:
        params["q"] = q
    return _hub_api("GET", "/items", params=params)


def get_item_detail(item_id: str) -> dict:
    return _hub_api("GET", f"/items/{item_id}")


def get_item_lineage(item_id: str) -> dict:
    return _hub_api("GET", f"/items/{item_id}/lineage")


def get_item_version_snapshot(item_id: str, version: str) -> dict:
    return _hub_api("GET", f"/items/{item_id}/versions/{version}")


def _agent_snapshot_payload(config: Any, skill_repo: Any) -> dict:
    return snapshot_from_resolved_config(resolve_agent_config(config, skill_repo=skill_repo)).model_dump(mode="json")


def _load_repo_publish_material(user_id: str, user_repo: Any, agent_config_repo: Any) -> Any:
    user = user_repo.get_by_id(user_id)
    if user is None or user.agent_config_id is None:
        raise RuntimeError(f"Agent user {user_id} is missing agent_config_id")
    config = agent_config_repo.get_agent_config(user.agent_config_id)
    if config is None:
        raise RuntimeError(f"Agent config not found for user {user_id}")
    return config


def publish(
    user_id: str,
    type_: str,
    bump_type: BumpType,
    release_notes: str,
    tags: list[str],
    visibility: str,
    publisher_user_id: str,
    publisher_username: str,
    user_repo: Any = None,
    agent_config_repo: Any = None,
    skill_repo: Any = None,
) -> dict:
    """Publish an AgentConfig snapshot to the Hub."""
    if user_repo is None or agent_config_repo is None:
        raise RuntimeError("user_repo and agent_config_repo are required for publish()")
    if skill_repo is None:
        raise RuntimeError("skill_repo is required for publish()")

    config = _load_repo_publish_material(user_id, user_repo, agent_config_repo)
    snapshot = _agent_snapshot_payload(config, skill_repo)
    meta = copy.deepcopy(config.meta)

    new_version = bump_semver(config.version, bump_type)

    slug = config.name.lower().replace(" ", "-")

    source = meta.get("source", {})
    parent_item_id = source.get("marketplace_item_id")
    parent_version = source.get("source_version")

    result = _hub_api(
        "POST",
        "/publish",
        json={
            "slug": slug,
            "type": type_,
            "name": config.name,
            "description": config.description,
            "version": new_version,
            "release_notes": release_notes,
            "tags": tags,
            "visibility": visibility,
            "snapshot": snapshot,
            "parent_item_id": parent_item_id,
            "parent_version": parent_version,
            "publisher_user_id": publisher_user_id,
            "publisher_username": publisher_username,
        },
    )

    meta["version"] = new_version
    meta["status"] = "active"
    if "source" not in meta:
        meta["source"] = {}
    meta["source"]["marketplace_item_id"] = result.get("item_id")
    meta["source"]["source_version"] = new_version
    meta["source"]["source_at"] = int(time.time() * 1000)
    meta["source"]["modified"] = False
    # @@@repo-publish-only - marketplace publish is now a repo-backed web path, not a local member-dir snapshot path.
    user = user_repo.get_by_id(user_id)
    if user is None or user.agent_config_id is None:
        raise RuntimeError(f"Agent user {user_id} is missing agent_config_id")
    owner_user_id = getattr(user, "owner_user_id", None)
    if owner_user_id is None:
        raise RuntimeError(f"Agent user {user_id} is missing owner_user_id")
    agent_config_repo.save_agent_config(config.model_copy(update={"status": "active", "version": new_version, "meta": meta}))

    return result


def apply_item(
    item_id: str,
    owner_user_id: str = "system",
    user_repo: Any = None,
    agent_config_repo: Any = None,
    skill_repo: Any = None,
) -> dict:
    """Apply a Hub item into the owner account.

    The Hub endpoint is /download; Mycel product semantics are save-to-Library
    or add Agent User.
    """
    result = _hub_api("POST", f"/items/{item_id}/download")
    snapshot = _required_object(result.get("snapshot"), label="Hub download snapshot")
    item = _required_object(result.get("item"), label="Hub download item")
    source_version = _required_text(result.get("version"), label="Hub download version")
    item_type = _required_text(item.get("type"), label="Hub item type")

    now = int(time.time() * 1000)

    if item_type == "skill":
        content = _required_text(snapshot.get("content"), label="Skill snapshot content")
        skill_metadata = _skill_metadata_from_content(content)
        skill_files = _skill_files_from_snapshot(snapshot)
        if skill_repo is None:
            raise RuntimeError("skill_repo is required to save a skill to Library")
        slug = _required_text(item.get("slug"), label="Hub item slug")
        if "/" in slug or "\\" in slug or slug in {"", ".", ".."}:
            raise ValueError(f"Invalid slug: {slug}")
        skill_name = str(skill_metadata["name"]).strip()
        owner_skills = skill_repo.list_for_owner(owner_user_id)
        existing_skill = _hub_source_skill(owner_skills, item_id)
        if existing_skill is not None and existing_skill.name != skill_name:
            raise ValueError("Skill snapshot frontmatter name must match existing Skill name")
        if existing_skill is None:
            skill_id = generate_skill_id()
            if skill_repo.get_by_id(owner_user_id, skill_id) is not None:
                raise RuntimeError("Generated Skill id already exists")
            for skill in owner_skills:
                if skill.name == skill_name:
                    raise ValueError("Skill name already exists under a different Library id")
        else:
            skill_id = existing_skill.id
        skill_description = _skill_description_from_metadata(skill_metadata)
        publisher = _required_text(item.get("publisher_username"), label="Hub item publisher_username")
        timestamp = datetime.now(UTC)
        source = {
            "marketplace_item_id": item_id,
            "source_version": source_version,
            "source_at": now,
            "publisher": publisher,
        }
        skill = skill_repo.upsert(
            Skill(
                id=skill_id,
                owner_user_id=owner_user_id,
                name=skill_name,
                description=skill_description,
                source=source,
                created_at=timestamp,
                updated_at=timestamp,
            )
        )
        package_hash = build_skill_package_hash(content, skill_files)
        package = skill_repo.create_package(
            SkillPackage(
                id=package_hash.removeprefix("sha256:"),
                owner_user_id=owner_user_id,
                skill_id=skill.id,
                version=source_version,
                hash=package_hash,
                manifest=build_skill_package_manifest(content, skill_files),
                skill_md=content,
                files=skill_files,
                source=source,
                created_at=timestamp,
            )
        )
        skill_repo.select_package(owner_user_id, skill.id, package.id)

        return {"resource_id": skill.id, "package_id": package.id, "type": "skill", "version": source_version}

    if item_type == "agent":
        raise ValueError("Marketplace agent items are not supported; apply Agent user items instead")

    if item_type == HUB_AGENT_USER_ITEM_TYPE:
        if user_repo is None or agent_config_repo is None:
            raise RuntimeError("user_repo and agent_config_repo are required to apply marketplace user snapshot")

        user_id = _snapshot_apply.apply_snapshot(
            snapshot=snapshot,
            marketplace_item_id=item_id,
            source_version=source_version,
            owner_user_id=owner_user_id,
            user_repo=user_repo,
            agent_config_repo=agent_config_repo,
            skill_repo=skill_repo,
        )
        return {"user_id": user_id, "type": "user", "version": source_version}

    raise ValueError(f"Unsupported item type: {item_type}")


def upgrade(
    user_id: str,
    item_id: str,
    owner_user_id: str,
    user_repo: Any = None,
    agent_config_repo: Any = None,
    skill_repo: Any = None,
) -> dict:
    """Upgrade a marketplace-sourced Agent user."""
    if user_repo is None or agent_config_repo is None:
        raise RuntimeError("user_repo and agent_config_repo are required to upgrade marketplace user snapshot")

    result = _hub_api("POST", f"/items/{item_id}/download")
    snapshot = result["snapshot"]
    source_version = result["version"]

    _snapshot_apply.apply_snapshot(
        snapshot=snapshot,
        marketplace_item_id=item_id,
        source_version=source_version,
        owner_user_id=owner_user_id,
        existing_user_id=user_id,
        user_repo=user_repo,
        agent_config_repo=agent_config_repo,
        skill_repo=skill_repo,
    )

    return {"user_id": user_id, "version": source_version}


def check_updates(items: list[dict]) -> dict:
    """Check for newer versions of marketplace-sourced items."""
    return _hub_api("POST", "/check-updates", json={"items": items})
