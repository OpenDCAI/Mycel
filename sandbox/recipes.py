from __future__ import annotations

from typing import Any


def humanize_recipe_provider(name: str) -> str:
    return " ".join(
        part[:1].upper() + part[1:]
        for part in name.replace("-", "_").split("_")
        if part
    )


def default_recipe_id(provider_name: str) -> str:
    return f"{provider_name}:default"


def lark_cli_recipe_id(provider_name: str) -> str:
    return f"{provider_name}:lark-cli"


def default_recipe_name(provider_name: str) -> str:
    return f"{humanize_recipe_provider(provider_name)} Default"


def lark_cli_recipe_name(provider_name: str) -> str:
    return f"{humanize_recipe_provider(provider_name)} + Lark CLI"


def recipe_features(recipe_id: str | None) -> dict[str, bool]:
    if not recipe_id:
        return {}
    if recipe_id.endswith(":lark-cli"):
        return {"lark_cli": True}
    return {}


def normalize_recipe_id(provider_name: str, recipe_id: str | None) -> str:
    return recipe_id or default_recipe_id(provider_name)


def resolve_builtin_recipe(provider_name: str, recipe_id: str | None = None) -> dict[str, Any]:
    resolved_id = normalize_recipe_id(provider_name, recipe_id)
    if resolved_id == lark_cli_recipe_id(provider_name):
        return {
            "id": resolved_id,
            "name": lark_cli_recipe_name(provider_name),
            "desc": f"Lark CLI bootstrap for {provider_name}",
            "provider_name": provider_name,
            "features": {"lark_cli": True},
        }
    return {
        "id": default_recipe_id(provider_name),
        "name": default_recipe_name(provider_name),
        "desc": f"Default recipe for {provider_name}",
        "provider_name": provider_name,
        "features": {},
    }


def list_builtin_recipes(sandbox_types: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for sandbox in sandbox_types:
        provider_name = str(sandbox["name"])
        available = bool(sandbox.get("available", False))
        default_item = resolve_builtin_recipe(provider_name)
        items.append(
            {
                **default_item,
                "type": "recipe",
                "available": available,
                "created_at": 0,
                "updated_at": 0,
            }
        )
        lark_item = resolve_builtin_recipe(provider_name, lark_cli_recipe_id(provider_name))
        items.append(
            {
                **lark_item,
                "type": "recipe",
                "available": available,
                "created_at": 0,
                "updated_at": 0,
            }
        )
    return items


def bootstrap_recipe(provider, *, session_id: str, recipe_id: str | None) -> None:
    features = recipe_features(recipe_id)
    if not features.get("lark_cli"):
        return

    verify = provider.execute(session_id, "command -v lark-cli", timeout_ms=10_000, cwd=_resolve_recipe_cwd(provider))
    if verify.exit_code == 0:
        return

    # @@@recipe-bootstrap-lark-cli - install lazily when the sandbox first resolves this recipe.
    install = provider.execute(
        session_id,
        "npm install -g @larksuite/cli",
        timeout_ms=300_000,
        cwd=_resolve_recipe_cwd(provider),
    )
    if install.exit_code != 0:
        error = install.error or install.output or "unknown bootstrap error"
        raise RuntimeError(f"Recipe bootstrap failed for {recipe_id}: {error}")


def _resolve_recipe_cwd(provider) -> str:
    for attr in ("default_cwd", "default_context_path", "mount_path"):
        val = getattr(provider, attr, None)
        if isinstance(val, str) and val:
            return val
    return "/home/user"
