"""Library CRUD for file-backed assets and DB-backed recipes."""

import json
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from backend.web.core.paths import library_dir
from backend.web.services import sandbox_service
from sandbox.recipes import FEATURE_CATALOG, normalize_recipe_snapshot
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
    snapshot = normalize_recipe_snapshot(provider_type, data)
    return {
        **snapshot,
        "type": "recipe",
        "provider_type": provider_type,
        "created_at": int(data.get("created_at") or 0),
        "updated_at": int(data.get("updated_at") or 0),
        "available": True,
        "builtin": builtin,
    }


def _merge_recipe_override(base: dict[str, Any], override: dict[str, Any] | None) -> dict[str, Any]:
    if not override:
        return base
    return _normalize_recipe_item(
        {
            **base,
            **override,
            "features": {
                **(base.get("features") or {}),
                **(override.get("features") or {}),
            },
            "created_at": base.get("created_at", 0),
            "updated_at": override.get("updated_at", base.get("updated_at", 0)),
        },
        builtin=True,
    )


def _require_recipe_repo(recipe_repo: RecipeRepo | None) -> RecipeRepo:
    if recipe_repo is None:
        raise ValueError("recipe_repo is required for recipe operations")
    return recipe_repo


def list_library(
    resource_type: str,
    owner_user_id: str | None = None,
    recipe_repo: RecipeRepo | None = None,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    if resource_type == "recipe":
        owner_user_id = _require_recipe_owner(owner_user_id)
        recipe_repo = _require_recipe_repo(recipe_repo)
        stored_rows = {row["recipe_id"]: row for row in recipe_repo.list_by_owner(owner_user_id)}
        items = []
        builtin_ids: set[str] = set()
        for recipe in list_default_recipes():
            builtin_ids.add(str(recipe["id"]))
            override_row = stored_rows.get(str(recipe["id"]))
            override = override_row["data"] if override_row and override_row["kind"] == "override" else None
            items.append(_merge_recipe_override(recipe, override))
        for row in stored_rows.values():
            if row["kind"] != "custom":
                continue
            recipe_id = str(row["recipe_id"]).strip()
            if not recipe_id or recipe_id in builtin_ids:
                continue
            items.append(_normalize_recipe_item(row["data"], builtin=False))
        return items
    if resource_type == "skill":
        skills_dir = LIBRARY_DIR / "skills"
        if skills_dir.exists():
            for d in sorted(skills_dir.iterdir()):
                if d.is_dir():
                    meta = _read_json(d / "meta.json", {})
                    results.append(
                        {
                            "id": d.name,
                            "type": "skill",
                            "name": meta.get("name", d.name),
                            "desc": meta.get("desc", ""),
                            "created_at": meta.get("created_at", 0),
                            "updated_at": meta.get("updated_at", 0),
                        }
                    )
    elif resource_type == "agent":
        agents_dir = LIBRARY_DIR / "agents"
        if agents_dir.exists():
            for f in sorted(agents_dir.glob("*.md")):
                meta = _read_json(f.with_suffix(".json"), {})
                results.append(
                    {
                        "id": f.stem,
                        "type": "agent",
                        "name": meta.get("name", f.stem),
                        "desc": meta.get("desc", ""),
                        "created_at": meta.get("created_at", 0),
                        "updated_at": meta.get("updated_at", 0),
                    }
                )
    elif resource_type == "mcp":
        mcp_data = _read_json(LIBRARY_DIR / ".mcp.json", {"mcpServers": {}})
        for name, cfg in mcp_data.get("mcpServers", {}).items():
            results.append(
                {
                    "id": name,
                    "type": "mcp",
                    "name": name,
                    "desc": cfg.get("desc", ""),
                    "created_at": cfg.get("created_at", 0),
                    "updated_at": cfg.get("updated_at", 0),
                }
            )
    return results


def list_default_recipes() -> list[dict[str, Any]]:
    return sandbox_service.list_default_recipes()


def create_resource(
    resource_type: str,
    name: str,
    desc: str = "",
    category: str = "",
    features: dict[str, bool] | None = None,
    owner_user_id: str | None = None,
    recipe_repo: RecipeRepo | None = None,
) -> dict[str, Any]:
    now = int(time.time() * 1000)
    cat = category or "未分类"
    if resource_type == "recipe":
        owner_user_id = _require_recipe_owner(owner_user_id)
        recipe_repo = _require_recipe_repo(recipe_repo)
        provider_type = cat.strip()
        if not provider_type:
            raise ValueError("Recipe provider_type is required")
        feature_source = features if isinstance(features, dict) else {}
        feature_values = {key: bool(feature_source.get(key, False)) for key in FEATURE_CATALOG}
        recipe_id = f"{provider_type}:custom:{uuid.uuid4().hex[:8]}"
        item = _normalize_recipe_item(
            {
                "id": recipe_id,
                "name": name,
                "desc": desc,
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
        rid = name.lower().replace(" ", "-")
        skill_dir = LIBRARY_DIR / "skills" / rid
        skill_dir.mkdir(parents=True, exist_ok=True)
        _write_json(
            skill_dir / "meta.json",
            {
                "name": name,
                "desc": desc,
                "category": cat,
                "created_at": now,
                "updated_at": now,
            },
        )
        (skill_dir / "SKILL.md").write_text(f"# {name}\n\n{desc}\n", encoding="utf-8")
        return {"id": rid, "type": "skill", "name": name, "desc": desc, "created_at": now, "updated_at": now}
    elif resource_type == "agent":
        rid = name.lower().replace(" ", "-")
        agents_dir = LIBRARY_DIR / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        _write_json(
            agents_dir / f"{rid}.json",
            {
                "name": name,
                "desc": desc,
                "category": cat,
                "created_at": now,
                "updated_at": now,
            },
        )
        (agents_dir / f"{rid}.md").write_text(f"---\nname: {rid}\ndescription: {desc}\n---\n\n# {name}\n", encoding="utf-8")
        return {"id": rid, "type": "agent", "name": name, "desc": desc, "created_at": now, "updated_at": now}
    elif resource_type == "mcp":
        mcp_path = LIBRARY_DIR / ".mcp.json"
        mcp_data = _read_json(mcp_path, {"mcpServers": {}})
        mcp_data["mcpServers"][name] = {
            "desc": desc,
            "category": cat,
            "created_at": now,
            "updated_at": now,
        }
        _write_json(mcp_path, mcp_data)
        return {"id": name, "type": "mcp", "name": name, "desc": desc, "created_at": now, "updated_at": now}
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
        base = next((item for item in list_default_recipes() if item["id"] == resource_id), None)
        if base is not None:
            row = recipe_repo.get(owner_user_id, resource_id)
            override = row["data"] if row and row["kind"] == "override" else {}
            override.update(updates)
            override["updated_at"] = now
            recipe_repo.upsert(
                owner_user_id=owner_user_id,
                recipe_id=resource_id,
                kind="override",
                provider_type=str(base["provider_type"]),
                data=override,
                created_at=int(base.get("created_at", now)),
            )
            return _merge_recipe_override(base, override)
        row = recipe_repo.get(owner_user_id, resource_id)
        if row is None or row["kind"] != "custom":
            return None
        current = row["data"]
        current.update(updates)
        current["updated_at"] = now
        recipe_repo.upsert(
            owner_user_id=owner_user_id,
            recipe_id=resource_id,
            kind="custom",
            provider_type=str(current["provider_type"]),
            data=current,
            created_at=int(row["created_at"]),
        )
        return _normalize_recipe_item(current, builtin=False)
    if resource_type == "skill":
        meta_path = LIBRARY_DIR / "skills" / resource_id / "meta.json"
        if not meta_path.exists():
            return None
        meta = _read_json(meta_path, {})
        meta.update(updates)
        meta["updated_at"] = now
        _write_json(meta_path, meta)
        return {
            "id": resource_id,
            "type": "skill",
            "name": meta.get("name", resource_id),
            "desc": meta.get("desc", ""),
            "created_at": meta.get("created_at", 0),
            "updated_at": now,
        }
    elif resource_type == "agent":
        meta_path = LIBRARY_DIR / "agents" / f"{resource_id}.json"
        if not meta_path.exists():
            return None
        meta = _read_json(meta_path, {})
        meta.update(updates)
        meta["updated_at"] = now
        _write_json(meta_path, meta)
        return {
            "id": resource_id,
            "type": "agent",
            "name": meta.get("name", resource_id),
            "desc": meta.get("desc", ""),
            "created_at": meta.get("created_at", 0),
            "updated_at": now,
        }
    elif resource_type == "mcp":
        mcp_path = LIBRARY_DIR / ".mcp.json"
        mcp_data = _read_json(mcp_path, {"mcpServers": {}})
        if resource_id not in mcp_data.get("mcpServers", {}):
            return None
        mcp_data["mcpServers"][resource_id].update(updates)
        mcp_data["mcpServers"][resource_id]["updated_at"] = now
        _write_json(mcp_path, mcp_data)
        entry = mcp_data["mcpServers"][resource_id]
        return {
            "id": resource_id,
            "type": "mcp",
            "name": entry.get("name", resource_id),
            "desc": entry.get("desc", ""),
            "created_at": entry.get("created_at", 0),
            "updated_at": now,
        }
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
        base = next((item for item in list_default_recipes() if item["id"] == resource_id), None)
        if base is not None:
            recipe_repo.delete(owner_user_id, resource_id)
            return True
        row = recipe_repo.get(owner_user_id, resource_id)
        if row is None or row["kind"] != "custom":
            return False
        recipe_repo.delete(owner_user_id, resource_id)
        return True
    if resource_type == "skill":
        target = LIBRARY_DIR / "skills" / resource_id
        if not target.is_dir():
            return False
        shutil.rmtree(target)
        return True
    elif resource_type == "agent":
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
    elif resource_type == "mcp":
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
    results: list[dict[str, str]] = []
    if resource_type == "recipe":
        owner_user_id = _require_recipe_owner(owner_user_id)
        return [
            {"name": item["name"], "desc": item["desc"]}
            for item in list_library("recipe", owner_user_id=owner_user_id, recipe_repo=recipe_repo)
        ]
    if resource_type == "skill":
        skills_dir = LIBRARY_DIR / "skills"
        if skills_dir.exists():
            for d in sorted(skills_dir.iterdir()):
                if d.is_dir():
                    meta = _read_json(d / "meta.json", {})
                    results.append({"name": meta.get("name", d.name), "desc": meta.get("desc", "")})
    elif resource_type == "agent":
        agents_dir = LIBRARY_DIR / "agents"
        if agents_dir.exists():
            for f in sorted(agents_dir.glob("*.md")):
                meta = _read_json(f.with_suffix(".json"), {})
                results.append({"name": meta.get("name", f.stem), "desc": meta.get("desc", "")})
    elif resource_type == "mcp":
        mcp_data = _read_json(LIBRARY_DIR / ".mcp.json", {"mcpServers": {}})
        for name, cfg in mcp_data.get("mcpServers", {}).items():
            results.append({"name": name, "desc": cfg.get("desc", "")})
    return results


def get_mcp_server_config(name: str) -> dict[str, Any] | None:
    """Get a single MCP server config from Library .mcp.json."""
    mcp_data = _read_json(LIBRARY_DIR / ".mcp.json", {"mcpServers": {}})
    return mcp_data.get("mcpServers", {}).get(name)


def get_library_skill_desc(name: str) -> str:
    """Get skill description from Library by name."""
    skills_dir = LIBRARY_DIR / "skills"
    if not skills_dir.exists():
        return ""
    for d in skills_dir.iterdir():
        if d.is_dir():
            meta = _read_json(d / "meta.json", {})
            if meta.get("name") == name:
                return meta.get("desc", "")
    return ""


def get_library_agent_desc(name: str) -> str:
    """Get agent description from Library by name."""
    agents_dir = LIBRARY_DIR / "agents"
    if not agents_dir.exists():
        return ""
    # Try exact match on filename stem
    json_path = agents_dir / f"{name}.json"
    if json_path.exists():
        meta = _read_json(json_path, {})
        return meta.get("desc", "")
    # Try matching by name field
    for f in agents_dir.glob("*.json"):
        meta = _read_json(f, {})
        if meta.get("name") == name:
            return meta.get("desc", "")
    return ""


def get_resource_used_by(
    resource_type: str,
    resource_name: str,
    owner_user_id: str,
    *,
    user_repo: Any = None,
) -> list[str]:
    """Return agent user names under the owner that use a given resource."""
    from backend.web.services.member_service import list_members

    config_key = {"skill": "skills", "mcp": "mcps", "agent": "subAgents"}.get(resource_type, "")
    if not config_key:
        return []
    names: list[str] = []
    for member in list_members(owner_user_id, user_repo=user_repo):
        items = member.get("config", {}).get(config_key, [])
        if any(i.get("name") == resource_name for i in items):
            names.append(member.get("name", member.get("id", "unknown")))
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
    if resource_type == "skill":
        path = LIBRARY_DIR / "skills" / resource_id / "SKILL.md"
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""
    elif resource_type == "agent":
        path = LIBRARY_DIR / "agents" / f"{resource_id}.md"
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""
    elif resource_type == "mcp":
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
    if resource_type == "skill":
        skill_dir = LIBRARY_DIR / "skills" / resource_id
        if not skill_dir.is_dir():
            return False
        (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
        meta_path = skill_dir / "meta.json"
        meta = _read_json(meta_path, {})
        meta["updated_at"] = now
        _write_json(meta_path, meta)
        return True
    elif resource_type == "agent":
        md_path = LIBRARY_DIR / "agents" / f"{resource_id}.md"
        json_path = LIBRARY_DIR / "agents" / f"{resource_id}.json"
        if not json_path.exists():
            return False
        md_path.write_text(content, encoding="utf-8")
        meta = _read_json(json_path, {})
        meta["updated_at"] = now
        _write_json(json_path, meta)
        return True
    elif resource_type == "mcp":
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
