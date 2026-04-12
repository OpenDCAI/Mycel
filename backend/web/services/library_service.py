"""Library CRUD for file-backed assets and DB-backed recipes."""

import json
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from backend.web.core.paths import library_dir
from backend.web.services import sandbox_service
from sandbox.recipes import FEATURE_CATALOG, default_recipe_snapshot, normalize_recipe_snapshot, provider_type_from_name
from storage.contracts import RecipeRepo

LIBRARY_DIR = library_dir()


def _read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default if default is not None else {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default if default is not None else {}


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _require_recipe_owner(owner_user_id: str | None) -> str:
    # @@@recipe-user-scope - custom recipes and builtin overrides are account-scoped resources.
    # Callers must pass owner_user_id for recipe operations so one user's edits never leak into another's library.
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
        "type": "recipe",
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


def _file_resource_content_path(resource_type: str, resource_id: str) -> Path | None:
    if resource_type == "skill":
        return LIBRARY_DIR / "skills" / resource_id / "SKILL.md"
    if resource_type == "agent":
        return LIBRARY_DIR / "agents" / f"{resource_id}.md"
    return None


def _file_resource_meta_path(resource_type: str, resource_id: str) -> Path | None:
    if resource_type == "skill":
        return LIBRARY_DIR / "skills" / resource_id / "meta.json"
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
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    if resource_type == "recipe":
        owner_user_id = _require_recipe_owner(owner_user_id)
        recipe_repo = _require_recipe_repo(recipe_repo)
        return [
            _normalize_recipe_item(row["data"], builtin=bool(row["data"].get("builtin")))
            for row in sorted(recipe_repo.list_by_owner(owner_user_id), key=lambda item: str(item["recipe_id"]))
        ]
    if resource_type == "skill":
        skills_dir = LIBRARY_DIR / "skills"
        if skills_dir.exists():
            for d in sorted(skills_dir.iterdir()):
                if d.is_dir():
                    meta = _read_json(d / "meta.json", {})
                    results.append(_library_resource_item("skill", d.name, meta))
    elif resource_type == "agent":
        agents_dir = LIBRARY_DIR / "agents"
        if agents_dir.exists():
            for f in sorted(agents_dir.glob("*.md")):
                meta = _read_json(f.with_suffix(".json"), {})
                results.append(_library_resource_item("agent", f.stem, meta))
    elif resource_type == "mcp":
        mcp_data = _read_json(LIBRARY_DIR / ".mcp.json", {"mcpServers": {}})
        for name, cfg in mcp_data.get("mcpServers", {}).items():
            results.append(_library_resource_item("mcp", name, cfg, name=name))
    return results


def seed_default_recipes(
    owner_user_id: str,
    *,
    recipe_repo: RecipeRepo | None = None,
    sandbox_types: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    owner_user_id = _require_recipe_owner(owner_user_id)
    recipe_repo = _require_recipe_repo(recipe_repo)
    now = int(time.time() * 1000)
    items: list[dict[str, Any]] = []
    source_sandboxes = sandbox_types if sandbox_types is not None else sandbox_service.available_sandbox_types()
    for sandbox in source_sandboxes:
        provider_name = str(sandbox.get("name") or "").strip()
        if not provider_name:
            continue
        provider_type = str(sandbox.get("provider") or provider_type_from_name(provider_name)).strip()
        recipe = {
            **default_recipe_snapshot(provider_type, provider_name=provider_name),
            "type": "recipe",
            "provider_name": provider_name,
            "provider_type": provider_type,
            "available": bool(sandbox.get("available", True)),
            "created_at": now,
            "updated_at": now,
        }
        existing = recipe_repo.get(owner_user_id, str(recipe["id"]))
        if existing is None or _recipe_row_needs_repair(existing, provider_name=provider_name, provider_type=provider_type):
            recipe_repo.upsert(
                owner_user_id=owner_user_id,
                recipe_id=str(recipe["id"]),
                kind="custom",
                provider_type=provider_type,
                data=recipe,
                created_at=now,
            )
        row = recipe_repo.get(owner_user_id, str(recipe["id"]))
        if row is None:
            raise RuntimeError(f"failed to seed recipe {recipe['id']}")
        items.append(_normalize_recipe_item(row["data"], builtin=bool(row["data"].get("builtin"))))
    return items


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
    for sandbox in sandbox_service.available_sandbox_types():
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
) -> dict[str, Any]:
    now = int(time.time() * 1000)
    cat = category or "未分类"
    if resource_type == "recipe":
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
    if resource_type in {"skill", "agent"}:
        rid = name.lower().replace(" ", "-")
        content_path = _file_resource_content_path(resource_type, rid)
        meta_path = _file_resource_meta_path(resource_type, rid)
        if content_path is None or meta_path is None:
            raise ValueError(f"Unknown resource type: {resource_type}")
        content_path.parent.mkdir(parents=True, exist_ok=True)
        meta = {"name": name, "desc": desc, "category": cat, "created_at": now, "updated_at": now}
        _write_json(meta_path, meta)
        content = f"# {name}\n\n{desc}\n" if resource_type == "skill" else f"---\nname: {rid}\ndescription: {desc}\n---\n\n# {name}\n"
        content_path.write_text(content, encoding="utf-8")
        return _library_resource_item(resource_type, rid, meta)
    if resource_type == "mcp":
        mcp_path = LIBRARY_DIR / ".mcp.json"
        mcp_data = _read_json(mcp_path, {"mcpServers": {}})
        meta = {
            "desc": desc,
            "category": cat,
            "created_at": now,
            "updated_at": now,
        }
        mcp_data["mcpServers"][name] = meta
        _write_json(mcp_path, mcp_data)
        return _library_resource_item("mcp", name, meta, name=name)
    raise ValueError(f"Unknown resource type: {resource_type}")


def update_resource(
    resource_type: str,
    resource_id: str,
    owner_user_id: str | None = None,
    recipe_repo: RecipeRepo | None = None,
    **fields: Any,
) -> dict[str, Any] | None:
    allowed = {"name", "desc", "features"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    now = int(time.time() * 1000)
    if resource_type == "recipe":
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
    if resource_type in {"skill", "agent"}:
        meta_path = _file_resource_meta_path(resource_type, resource_id)
        if meta_path is None or not meta_path.exists():
            return None
        meta = _read_json(meta_path, {})
        meta.update(updates)
        meta["updated_at"] = now
        _write_json(meta_path, meta)
        return _library_resource_item(resource_type, resource_id, meta, updated_at=now)
    if resource_type == "mcp":
        mcp_path = LIBRARY_DIR / ".mcp.json"
        mcp_data = _read_json(mcp_path, {"mcpServers": {}})
        if resource_id not in mcp_data.get("mcpServers", {}):
            return None
        mcp_data["mcpServers"][resource_id].update(updates)
        mcp_data["mcpServers"][resource_id]["updated_at"] = now
        _write_json(mcp_path, mcp_data)
        entry = mcp_data["mcpServers"][resource_id]
        return _library_resource_item("mcp", resource_id, entry, name=entry.get("name", resource_id), updated_at=now)
    return None


def delete_resource(
    resource_type: str,
    resource_id: str,
    owner_user_id: str | None = None,
    recipe_repo: RecipeRepo | None = None,
) -> bool:
    if resource_type == "recipe":
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
                "type": "recipe",
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
        target = LIBRARY_DIR / "skills" / resource_id
        if not target.is_dir():
            return False
        shutil.rmtree(target)
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
    if resource_type == "mcp":
        mcp_path = LIBRARY_DIR / ".mcp.json"
        mcp_data = _read_json(mcp_path, {"mcpServers": {}})
        if resource_id not in mcp_data.get("mcpServers", {}):
            return False
        del mcp_data["mcpServers"][resource_id]
        _write_json(mcp_path, mcp_data)
        return True
    return False


def list_library_names(
    resource_type: str,
    owner_user_id: str | None = None,
    recipe_repo: RecipeRepo | None = None,
) -> list[dict[str, str]]:
    """Lightweight name+desc list for Picker UI."""
    return [
        {"name": item["name"], "desc": item["desc"]}
        for item in list_library(resource_type, owner_user_id=owner_user_id, recipe_repo=recipe_repo)
    ]


def get_library_skill_desc(name: str) -> str:
    """Get skill description from Library by name."""
    return next((item["desc"] for item in list_library("skill") if item["name"] == name), "")


def get_resource_used_by(
    resource_type: str,
    resource_name: str,
    owner_user_id: str,
    *,
    user_repo: Any = None,
    agent_config_repo: Any = None,
) -> list[str]:
    """Return agent user names under the owner that use a given resource."""
    from backend.web.services.agent_user_service import list_agent_users

    config_key = {"skill": "skills", "mcp": "mcps", "agent": "subAgents"}.get(resource_type, "")
    if not config_key:
        return []
    names: list[str] = []
    for agent in list_agent_users(owner_user_id, user_repo=user_repo, agent_config_repo=agent_config_repo):
        items = agent.get("config", {}).get(config_key, [])
        if any(i.get("name") == resource_name for i in items):
            names.append(agent.get("name", agent.get("id", "unknown")))
    return names


def get_resource_content(
    resource_type: str,
    resource_id: str,
    owner_user_id: str | None = None,
    recipe_repo: RecipeRepo | None = None,
) -> str | None:
    """Read the .md content file for a skill or agent resource."""
    if resource_type == "recipe":
        owner_user_id = _require_recipe_owner(owner_user_id)
        for item in list_library("recipe", owner_user_id=owner_user_id, recipe_repo=recipe_repo):
            if item["id"] == resource_id:
                return json.dumps(item, ensure_ascii=False, indent=2)
        return None
    content_path = _file_resource_content_path(resource_type, resource_id)
    if content_path is not None:
        if content_path.exists():
            return content_path.read_text(encoding="utf-8")
        return ""
    if resource_type == "mcp":
        mcp_data = _read_json(LIBRARY_DIR / ".mcp.json", {"mcpServers": {}})
        cfg = mcp_data.get("mcpServers", {}).get(resource_id)
        if cfg is None:
            return None
        # Only return MCP config fields, not metadata
        meta_keys = {"desc", "category", "created_at", "updated_at", "name"}
        config_only = {k: v for k, v in cfg.items() if k not in meta_keys}
        if not config_only:
            # Return a template if no config exists yet
            config_only = {"command": "", "args": [], "env": {}}
        return json.dumps(config_only, ensure_ascii=False, indent=2)
    return None


def update_resource_content(resource_type: str, resource_id: str, content: str) -> bool:
    """Write the .md content file for a skill or agent resource."""
    now = int(time.time() * 1000)
    if resource_type == "recipe":
        return False
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
    if resource_type == "mcp":
        mcp_path = LIBRARY_DIR / ".mcp.json"
        mcp_data = _read_json(mcp_path, {"mcpServers": {}})
        if resource_id not in mcp_data.get("mcpServers", {}):
            return False
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            return False
        # Preserve metadata before overwriting with parsed config
        existing = mcp_data["mcpServers"][resource_id]
        meta_keys = {"desc", "category", "created_at", "name"}
        preserved = {k: existing[k] for k in meta_keys if k in existing}
        mcp_data["mcpServers"][resource_id] = {**parsed, **preserved, "updated_at": now}
        _write_json(mcp_path, mcp_data)
        return True
    return False
