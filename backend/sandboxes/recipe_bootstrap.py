from __future__ import annotations

import time
from typing import Any

from backend.sandboxes.inventory import available_sandbox_types
from sandbox.recipes import default_recipe_snapshot, normalize_recipe_snapshot, provider_type_from_name
from storage.contracts import RecipeRepo


def _require_recipe_owner(owner_user_id: str | None) -> str:
    if not owner_user_id:
        raise ValueError("owner_user_id is required for recipe operations")
    return str(owner_user_id or "")


def _require_recipe_repo(recipe_repo: RecipeRepo | None) -> RecipeRepo:
    if recipe_repo is None:
        raise ValueError("recipe_repo is required for recipe operations")
    return recipe_repo


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
    source_sandboxes = sandbox_types if sandbox_types is not None else available_sandbox_types()
    for sandbox in source_sandboxes:
        provider_name = str(sandbox.get("name") or "").strip()
        if not provider_name:
            continue
        provider_type = str(sandbox.get("provider") or provider_type_from_name(provider_name)).strip()
        recipe = {
            **default_recipe_snapshot(provider_type, provider_name=provider_name),
            "type": "sandbox-template",
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
