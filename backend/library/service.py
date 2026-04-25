"""Library CRUD for Skills, Agent templates, and sandbox templates."""

import json
import re
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from backend.library.paths import LIBRARY_DIR
from backend.sandboxes import provider_availability as sandbox_provider_availability
from backend.sandboxes.recipe_bootstrap import seed_default_recipes as seed_builtin_recipes
from config.agent_config_types import Skill, SkillPackage
from config.skill_package import build_skill_package_hash, build_skill_package_manifest
from sandbox.recipes import FEATURE_CATALOG, default_recipe_snapshot, normalize_recipe_snapshot, provider_type_from_name
from storage.contracts import RecipeRepo, SkillRepo

_SKILL_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_RESOURCE_TYPES = {"skill", "agent", "sandbox-template"}


def _require_resource_type(resource_type: str) -> None:
    if resource_type not in _RESOURCE_TYPES:
        raise ValueError(f"Unknown resource type: {resource_type}")


def _read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default if default is not None else {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Library JSON file must be valid JSON: {path}") from exc
    except OSError as exc:
        raise RuntimeError(f"Library JSON file could not be read: {path}") from exc


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _require_recipe_owner(owner_user_id: str | None) -> str:
    # @@@sandbox-template-user-scope - custom sandbox templates and builtin overrides are account-scoped resources.
    # Callers must pass owner_user_id so one user's template edits never leak into another user's library.
    if not owner_user_id:
        raise ValueError("owner_user_id is required for recipe operations")
    return str(owner_user_id or "")


def _normalize_recipe_item(data: dict[str, Any], *, builtin: bool) -> dict[str, Any]:
    provider_type = str(data.get("provider_type") or "").strip()
    if not provider_type:
        raise ValueError("recipe.provider_type is required")
    provider_name = str(data.get("provider_name") or data.get("id", "").split(":")[0] or provider_type).strip()
    snapshot = normalize_recipe_snapshot(provider_type, {**data, "provider_name": provider_name})
    return {
        **snapshot,
        "type": "sandbox-template",
        "provider_name": provider_name,
        "provider_type": provider_type,
        "created_at": int(data.get("created_at") or 0),
        "updated_at": int(data.get("updated_at") or 0),
        "available": True,
        "builtin": builtin,
    }


def _require_recipe_repo(recipe_repo: RecipeRepo | None) -> RecipeRepo:
    if recipe_repo is None:
        raise ValueError("recipe_repo is required for recipe operations")
    return recipe_repo


def _require_skill_owner(owner_user_id: str | None) -> str:
    if not owner_user_id:
        raise ValueError("owner_user_id is required for skill operations")
    return str(owner_user_id)


def _require_skill_repo(skill_repo: SkillRepo | None) -> SkillRepo:
    if skill_repo is None:
        raise ValueError("skill_repo is required for skill operations")
    return skill_repo


def _skill_frontmatter_name(content: str) -> str:
    # @@@skill-name-single-truth - runtime indexes Skills by SKILL.md frontmatter name, so Library name must not drift.
    match = _SKILL_FRONTMATTER_RE.search(content)
    if match is None:
        raise ValueError("Skill content must be a SKILL.md document with frontmatter")
    metadata = yaml.safe_load(match.group(1)) or {}
    if not isinstance(metadata, dict):
        raise ValueError("Skill content frontmatter must be a mapping")
    name = metadata.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Skill content frontmatter name is required")
    return name.strip()


def _now_dt() -> datetime:
    return datetime.now(UTC)


def _dt_millis(value: datetime) -> int:
    return int(value.timestamp() * 1000)


def _package_id(package_hash: str) -> str:
    return package_hash.removeprefix("sha256:")


def _selected_skill_package(owner_user_id: str, skill: Skill, skill_repo: SkillRepo) -> SkillPackage | None:
    if not skill.package_id:
        return None
    return skill_repo.get_package(owner_user_id, skill.package_id)


def _write_skill_package(
    owner_user_id: str,
    skill: Skill,
    content: str,
    files: dict[str, str],
    skill_repo: SkillRepo,
    *,
    version: str = "0.1.0",
    source: dict[str, Any] | None = None,
) -> SkillPackage:
    package_hash = build_skill_package_hash(content, files)
    package = skill_repo.create_package(
        SkillPackage(
            id=_package_id(package_hash),
            owner_user_id=owner_user_id,
            skill_id=skill.id,
            version=version,
            hash=package_hash,
            manifest=build_skill_package_manifest(content, files),
            skill_md=content,
            files=files,
            source=source or {},
            created_at=_now_dt(),
        )
    )
    skill_repo.select_package(owner_user_id, skill.id, package.id)
    return package


def _file_resource_content_path(resource_type: str, resource_id: str) -> Path | None:
    if resource_type == "agent":
        return LIBRARY_DIR / "agents" / f"{resource_id}.md"
    return None


def _file_resource_meta_path(resource_type: str, resource_id: str) -> Path | None:
    if resource_type == "agent":
        return LIBRARY_DIR / "agents" / f"{resource_id}.json"
    return None


def _library_resource_item(
    resource_type: str,
    resource_id: str,
    meta: dict[str, Any],
    *,
    name: str | None = None,
    updated_at: int | None = None,
) -> dict[str, Any]:
    return {
        "id": resource_id,
        "type": resource_type,
        "name": name if name is not None else meta.get("name", resource_id),
        "desc": meta.get("desc", ""),
        "created_at": meta.get("created_at", 0),
        "updated_at": updated_at if updated_at is not None else meta.get("updated_at", 0),
    }


def list_library(
    resource_type: str,
    owner_user_id: str | None = None,
    recipe_repo: RecipeRepo | None = None,
    skill_repo: SkillRepo | None = None,
) -> list[dict[str, Any]]:
    _require_resource_type(resource_type)
    results: list[dict[str, Any]] = []
    if resource_type == "sandbox-template":
        owner_user_id = _require_recipe_owner(owner_user_id)
        recipe_repo = _require_recipe_repo(recipe_repo)
        return [
            _normalize_recipe_item(row["data"], builtin=bool(row["data"].get("builtin")))
            for row in sorted(recipe_repo.list_by_owner(owner_user_id), key=lambda item: str(item["recipe_id"]))
        ]
    if resource_type == "skill":
        owner_user_id = _require_skill_owner(owner_user_id)
        skill_repo = _require_skill_repo(skill_repo)
        return [
            _library_resource_item(
                "skill",
                skill.id,
                {
                    "name": skill.name,
                    "desc": skill.description,
                    "created_at": _dt_millis(skill.created_at),
                    "updated_at": _dt_millis(skill.updated_at),
                },
            )
            for skill in sorted(skill_repo.list_for_owner(owner_user_id), key=lambda item: item.name.lower())
        ]
    if resource_type == "agent":
        agents_dir = LIBRARY_DIR / "agents"
        if agents_dir.exists():
            for f in sorted(agents_dir.glob("*.md")):
                meta = _read_json(f.with_suffix(".json"), {})
                results.append(_library_resource_item("agent", f.stem, meta))
    return results


seed_default_recipes = seed_builtin_recipes


def _recipe_row_needs_repair(row: dict[str, Any], *, provider_name: str, provider_type: str) -> bool:
    data = row.get("data")
    if not isinstance(data, dict):
        return True
    return (
        data.get("id") != f"{provider_name}:default"
        or data.get("provider_name") != provider_name
        or data.get("provider_type") != provider_type
        or not isinstance(data.get("features"), dict)
    )


def _resolve_recipe_provider(provider_name: str | None) -> tuple[str, str]:
    name = str(provider_name or "").strip()
    if not name:
        raise ValueError("Recipe provider_name is required")
    for sandbox in sandbox_provider_availability.available_sandbox_types():
        if str(sandbox.get("name") or "").strip() != name:
            continue
        provider_type = str(sandbox.get("provider") or "").strip()
        if not provider_type:
            raise ValueError(f"Sandbox provider {name!r} is missing provider type")
        return name, provider_type
    raise ValueError(f"Unknown sandbox provider: {name}")


def create_resource(
    resource_type: str,
    name: str,
    desc: str = "",
    category: str = "",
    features: dict[str, bool] | None = None,
    provider_name: str | None = None,
    owner_user_id: str | None = None,
    recipe_repo: RecipeRepo | None = None,
    skill_repo: SkillRepo | None = None,
) -> dict[str, Any]:
    now = int(time.time() * 1000)
    cat = category or "未分类"
    if resource_type == "sandbox-template":
        owner_user_id = _require_recipe_owner(owner_user_id)
        recipe_repo = _require_recipe_repo(recipe_repo)
        provider_name, provider_type = _resolve_recipe_provider(provider_name)
        feature_source = features if isinstance(features, dict) else {}
        feature_values = {key: bool(feature_source.get(key, False)) for key in FEATURE_CATALOG}
        recipe_id = f"{provider_name}:custom:{uuid.uuid4().hex[:8]}"
        item = _normalize_recipe_item(
            {
                "id": recipe_id,
                "name": name,
                "desc": desc,
                "provider_name": provider_name,
                "provider_type": provider_type,
                "features": feature_values,
                "created_at": now,
                "updated_at": now,
            },
            builtin=False,
        )
        recipe_repo.upsert(
            owner_user_id=owner_user_id,
            recipe_id=recipe_id,
            kind="custom",
            provider_type=provider_type,
            data=item,
            created_at=now,
        )
        return item
    if resource_type == "skill":
        owner_user_id = _require_skill_owner(owner_user_id)
        skill_repo = _require_skill_repo(skill_repo)
        rid = name.lower().replace(" ", "-")
        existing = skill_repo.get_by_id(owner_user_id, rid)
        if existing is not None and existing.name != name:
            raise ValueError("Skill id already exists with a different Skill name")
        timestamp = _now_dt()
        content = f"---\nname: {name}\ndescription: {desc}\n---\n\n{desc}\n"
        skill = skill_repo.upsert(
            Skill(
                id=rid,
                owner_user_id=owner_user_id,
                name=name,
                description=desc,
                created_at=timestamp,
                updated_at=timestamp,
            )
        )
        _write_skill_package(owner_user_id, skill, content, {}, skill_repo)
        return _library_resource_item(
            "skill",
            skill.id,
            {
                "name": skill.name,
                "desc": skill.description,
                "created_at": _dt_millis(skill.created_at),
                "updated_at": _dt_millis(skill.updated_at),
            },
        )
    if resource_type == "agent":
        rid = name.lower().replace(" ", "-")
        content_path = _file_resource_content_path(resource_type, rid)
        meta_path = _file_resource_meta_path(resource_type, rid)
        if content_path is None or meta_path is None:
            raise ValueError(f"Unknown resource type: {resource_type}")
        content_path.parent.mkdir(parents=True, exist_ok=True)
        meta = {"name": name, "desc": desc, "category": cat, "created_at": now, "updated_at": now}
        _write_json(meta_path, meta)
        content_path.write_text(f"---\nname: {rid}\ndescription: {desc}\n---\n\n# {name}\n", encoding="utf-8")
        return _library_resource_item(resource_type, rid, meta)
    raise ValueError(f"Unknown resource type: {resource_type}")


def update_resource(
    resource_type: str,
    resource_id: str,
    owner_user_id: str | None = None,
    recipe_repo: RecipeRepo | None = None,
    skill_repo: SkillRepo | None = None,
    *,
    name: str | None = None,
    desc: str | None = None,
    features: dict[str, bool] | None = None,
) -> dict[str, Any] | None:
    _require_resource_type(resource_type)
    updates = {key: value for key, value in {"name": name, "desc": desc, "features": features}.items() if value is not None}
    now = int(time.time() * 1000)
    if resource_type == "sandbox-template":
        owner_user_id = _require_recipe_owner(owner_user_id)
        recipe_repo = _require_recipe_repo(recipe_repo)
        row = recipe_repo.get(owner_user_id, resource_id)
        if row is None:
            return None
        current = dict(row["data"])
        current.update(updates)
        current["updated_at"] = now
        recipe_repo.upsert(
            owner_user_id=owner_user_id,
            recipe_id=resource_id,
            kind=str(row["kind"]),
            provider_type=str(current["provider_type"]),
            data=current,
            created_at=int(row["created_at"]),
        )
        return _normalize_recipe_item(current, builtin=False)
    if resource_type == "skill":
        owner_user_id = _require_skill_owner(owner_user_id)
        skill_repo = _require_skill_repo(skill_repo)
        current = skill_repo.get_by_id(owner_user_id, resource_id)
        if current is None:
            return None
        if name is not None and name != current.name:
            raise ValueError("Skill name is immutable; create a new Skill for a new name")
        updated = skill_repo.upsert(
            current.model_copy(
                update={
                    "name": current.name,
                    "description": desc if desc is not None else current.description,
                    "updated_at": _now_dt(),
                }
            )
        )
        return _library_resource_item(
            "skill",
            updated.id,
            {
                "name": updated.name,
                "desc": updated.description,
                "created_at": _dt_millis(updated.created_at),
                "updated_at": _dt_millis(updated.updated_at),
            },
            updated_at=_dt_millis(updated.updated_at),
        )
    if resource_type == "agent":
        meta_path = _file_resource_meta_path(resource_type, resource_id)
        if meta_path is None or not meta_path.exists():
            return None
        meta = _read_json(meta_path, {})
        meta.update(updates)
        meta["updated_at"] = now
        _write_json(meta_path, meta)
        return _library_resource_item(resource_type, resource_id, meta, updated_at=now)
    return None


def delete_resource(
    resource_type: str,
    resource_id: str,
    owner_user_id: str | None = None,
    recipe_repo: RecipeRepo | None = None,
    skill_repo: SkillRepo | None = None,
) -> bool:
    _require_resource_type(resource_type)
    if resource_type == "sandbox-template":
        owner_user_id = _require_recipe_owner(owner_user_id)
        recipe_repo = _require_recipe_repo(recipe_repo)
        row = recipe_repo.get(owner_user_id, resource_id)
        if row is None:
            return False
        data = row["data"]
        if data.get("builtin"):
            provider_name = str(data.get("provider_name") or resource_id.split(":")[0]).strip()
            provider_type = str(data.get("provider_type") or provider_type_from_name(provider_name)).strip()
            now = int(time.time() * 1000)
            reset = {
                **default_recipe_snapshot(provider_type, provider_name=provider_name),
                "type": "sandbox-template",
                "provider_name": provider_name,
                "provider_type": provider_type,
                "available": bool(data.get("available", True)),
                "created_at": int(row["created_at"]),
                "updated_at": now,
            }
            recipe_repo.upsert(
                owner_user_id=owner_user_id,
                recipe_id=resource_id,
                kind=str(row["kind"]),
                provider_type=provider_type,
                data=reset,
                created_at=int(row["created_at"]),
            )
            return True
        recipe_repo.delete(owner_user_id, resource_id)
        return True
    if resource_type == "skill":
        owner_user_id = _require_skill_owner(owner_user_id)
        skill_repo = _require_skill_repo(skill_repo)
        if skill_repo.get_by_id(owner_user_id, resource_id) is None:
            return False
        skill_repo.delete(owner_user_id, resource_id)
        return True
    if resource_type == "agent":
        md_path = LIBRARY_DIR / "agents" / f"{resource_id}.md"
        json_path = LIBRARY_DIR / "agents" / f"{resource_id}.json"
        found = False
        if md_path.exists():
            md_path.unlink()
            found = True
        if json_path.exists():
            json_path.unlink()
            found = True
        return found
    return False


def list_library_names(
    resource_type: str,
    owner_user_id: str | None = None,
    recipe_repo: RecipeRepo | None = None,
    skill_repo: SkillRepo | None = None,
) -> list[dict[str, str]]:
    """Lightweight name+desc list for Picker UI."""
    return [
        {"name": item["name"], "desc": item["desc"]}
        for item in list_library(resource_type, owner_user_id=owner_user_id, recipe_repo=recipe_repo, skill_repo=skill_repo)
    ]


def get_resource_used_by(
    resource_type: str,
    resource_name: str,
    owner_user_id: str,
    *,
    user_repo: Any = None,
    agent_config_repo: Any = None,
) -> list[str]:
    """Return agent user names under the owner that use a given resource."""
    _require_resource_type(resource_type)
    if user_repo is None or agent_config_repo is None:
        raise RuntimeError("user_repo and agent_config_repo are required for resource usage reads")
    config_attr = {"skill": "skills", "agent": "sub_agents"}.get(resource_type, "")
    if not config_attr:
        return []
    names: list[str] = []
    for agent in user_repo.list_by_owner_user_id(owner_user_id):
        agent_config_id = getattr(agent, "agent_config_id", None)
        if not agent_config_id:
            raise RuntimeError(f"Agent user {getattr(agent, 'id', 'unknown')} is missing agent_config_id")
        config = agent_config_repo.get_agent_config(agent_config_id)
        if config is None:
            raise RuntimeError(f"Agent config {agent_config_id} is missing for {getattr(agent, 'id', 'unknown')}")
        if any(getattr(item, "name", None) == resource_name for item in getattr(config, config_attr)):
            names.append(str(getattr(config, "name", None) or getattr(agent, "display_name", None) or getattr(agent, "id", "unknown")))
    return names


def get_resource_content(
    resource_type: str,
    resource_id: str,
    owner_user_id: str | None = None,
    recipe_repo: RecipeRepo | None = None,
    skill_repo: SkillRepo | None = None,
) -> str | None:
    """Read the .md content file for a skill or agent resource."""
    _require_resource_type(resource_type)
    if resource_type == "sandbox-template":
        owner_user_id = _require_recipe_owner(owner_user_id)
        for item in list_library("sandbox-template", owner_user_id=owner_user_id, recipe_repo=recipe_repo):
            if item["id"] == resource_id:
                return json.dumps(item, ensure_ascii=False, indent=2)
        return None
    if resource_type == "skill":
        owner_user_id = _require_skill_owner(owner_user_id)
        skill_repo = _require_skill_repo(skill_repo)
        skill = skill_repo.get_by_id(owner_user_id, resource_id)
        if skill is None:
            return None
        package = _selected_skill_package(owner_user_id, skill, skill_repo)
        if package is None:
            raise RuntimeError(f"Skill {resource_id} has no selected package")
        return package.skill_md
    content_path = _file_resource_content_path(resource_type, resource_id)
    if content_path is not None:
        if content_path.exists():
            return content_path.read_text(encoding="utf-8")
        return ""
    return None


def update_resource_content(
    resource_type: str,
    resource_id: str,
    content: str,
    owner_user_id: str | None = None,
    skill_repo: SkillRepo | None = None,
) -> bool:
    """Write the .md content file for a skill or agent resource."""
    _require_resource_type(resource_type)
    now = int(time.time() * 1000)
    if resource_type == "sandbox-template":
        return False
    if resource_type == "skill":
        owner_user_id = _require_skill_owner(owner_user_id)
        skill_repo = _require_skill_repo(skill_repo)
        current = skill_repo.get_by_id(owner_user_id, resource_id)
        if current is None:
            return False
        frontmatter_name = _skill_frontmatter_name(content)
        if frontmatter_name != current.name:
            raise ValueError("Skill content frontmatter name must match Skill name")
        current_package = _selected_skill_package(owner_user_id, current, skill_repo)
        files = current_package.files if current_package is not None else {}
        updated = skill_repo.upsert(current.model_copy(update={"updated_at": _now_dt()}))
        _write_skill_package(owner_user_id, updated, content, files, skill_repo)
        return True
    content_path = _file_resource_content_path(resource_type, resource_id)
    meta_path = _file_resource_meta_path(resource_type, resource_id)
    if content_path is not None and meta_path is not None:
        if resource_type == "skill" and not content_path.parent.is_dir():
            return False
        if resource_type == "agent" and not meta_path.exists():
            return False
        content_path.write_text(content, encoding="utf-8")
        meta = _read_json(meta_path, {})
        meta["updated_at"] = now
        _write_json(meta_path, meta)
        return True
    return False
