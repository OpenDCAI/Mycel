from __future__ import annotations

from copy import deepcopy
from typing import Any


FEATURE_CATALOG: dict[str, dict[str, str]] = {
    "lark_cli": {
        "key": "lark_cli",
        "name": "Lark CLI",
        "description": "在 sandbox 初始化时懒安装并校验。",
        "icon": "feishu",
    },
}


def provider_type_from_name(name: str) -> str:
    if name.startswith("daytona"):
        return "daytona"
    if name.startswith("docker"):
        return "docker"
    if name.startswith("e2b"):
        return "e2b"
    if name.startswith("agentbay"):
        return "agentbay"
    return "local"


def humanize_recipe_provider(name: str) -> str:
    return " ".join(
        part[:1].upper() + part[1:]
        for part in name.replace("-", "_").split("_")
        if part
    )


def default_recipe_id(provider_type: str) -> str:
    return f"{provider_type}:default"


def default_recipe_name(provider_type: str) -> str:
    return f"{humanize_recipe_provider(provider_type)} Default"


def default_recipe_snapshot(provider_type: str) -> dict[str, Any]:
    return {
        "id": default_recipe_id(provider_type),
        "name": default_recipe_name(provider_type),
        "desc": f"Default recipe for {provider_type}",
        "provider_type": provider_type,
        "features": {"lark_cli": False},
        "configurable_features": {"lark_cli": True},
        "feature_options": [deepcopy(FEATURE_CATALOG["lark_cli"])],
        "builtin": True,
    }


def normalize_recipe_snapshot(provider_type: str, recipe: dict[str, Any] | None = None) -> dict[str, Any]:
    base = default_recipe_snapshot(provider_type)
    if recipe is None:
        return base

    requested_type = str(recipe.get("provider_type") or provider_type).strip() or provider_type
    if requested_type != provider_type:
        raise RuntimeError(
            f"Recipe provider_type {requested_type!r} does not match selected provider_type {provider_type!r}"
        )

    requested_features = recipe.get("features")
    normalized_features = dict(base["features"])
    if isinstance(requested_features, dict):
        for key, value in requested_features.items():
            if key in FEATURE_CATALOG:
                normalized_features[key] = bool(value)

    return {
        **base,
        "id": str(recipe.get("id") or base["id"]),
        "name": str(recipe.get("name") or base["name"]),
        "desc": str(recipe.get("desc") or base["desc"]),
        "features": normalized_features,
        "builtin": bool(recipe.get("builtin", base["builtin"])),
    }


def recipe_features(recipe: dict[str, Any] | None) -> dict[str, bool]:
    if not recipe:
        return {}
    raw = recipe.get("features")
    if not isinstance(raw, dict):
        return {}
    return {
        key: bool(value)
        for key, value in raw.items()
        if key in FEATURE_CATALOG
    }


def list_builtin_recipes(sandbox_types: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    providers_by_type: dict[str, dict[str, Any]] = {}
    for sandbox in sandbox_types:
        provider_name = str(sandbox["name"])
        provider_type = str(sandbox.get("provider") or provider_type_from_name(provider_name))
        existing = providers_by_type.get(provider_type)
        if existing and not existing.get("available", False) and sandbox.get("available", False):
            providers_by_type[provider_type] = sandbox
            continue
        if existing:
            continue
        providers_by_type[provider_type] = sandbox

    for provider_type, sandbox in providers_by_type.items():
        available = bool(sandbox.get("available", False))
        item = default_recipe_snapshot(provider_type)
        items.append(
            {
                **item,
                "provider_type": provider_type,
                "type": "recipe",
                "available": available,
                "created_at": 0,
                "updated_at": 0,
            }
        )
    return items


def resolve_builtin_recipe(provider_type: str, recipe_id: str | None = None) -> dict[str, Any]:
    base = default_recipe_snapshot(provider_type)
    if recipe_id and recipe_id != base["id"]:
        raise RuntimeError(
            f"Unknown recipe id {recipe_id!r} for provider type {provider_type}. Builtin recipes only expose defaults."
        )
    return base


def bootstrap_recipe(provider, *, session_id: str, recipe: dict[str, Any] | None) -> None:
    features = recipe_features(recipe)
    if not features.get("lark_cli"):
        return

    verify = provider.execute(session_id, "command -v lark-cli", timeout_ms=10_000, cwd=_resolve_recipe_cwd(provider))
    if verify.exit_code == 0:
        return

    # @@@recipe-bootstrap-lark-cli - recipe features bootstrap lazily on first real sandbox resolution.
    install = provider.execute(
        session_id,
        "npm install -g @larksuite/cli",
        timeout_ms=300_000,
        cwd=_resolve_recipe_cwd(provider),
    )
    if install.exit_code != 0:
        recipe_name = recipe.get("name") if isinstance(recipe, dict) else None
        error = install.error or install.output or "unknown bootstrap error"
        raise RuntimeError(f"Recipe bootstrap failed for {recipe_name or 'unknown recipe'}: {error}")


def _resolve_recipe_cwd(provider) -> str:
    for attr in ("default_cwd", "default_context_path", "mount_path"):
        val = getattr(provider, attr, None)
        if isinstance(val, str) and val:
            return val
    return "/home/user"
