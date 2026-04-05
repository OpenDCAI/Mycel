"""Resolve + persist per-member new-thread config defaults."""

from __future__ import annotations

from typing import Any

from backend.web.services import sandbox_service
from backend.web.services.library_service import list_library
from sandbox.recipes import provider_type_from_name


def normalize_launch_config_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "create_mode": "existing" if payload.get("create_mode") == "existing" else "new",
        "provider_config": str(payload.get("provider_config") or "").strip(),
        "recipe": payload.get("recipe") if isinstance(payload.get("recipe"), dict) else None,
        "lease_id": str(payload.get("lease_id") or "").strip() or None,
        "model": str(payload.get("model") or "").strip() or None,
        "workspace": str(payload.get("workspace") or "").strip() or None,
    }


def save_last_confirmed_config(app: Any, owner_user_id: str, member_id: str, payload: dict[str, Any]) -> None:
    app.state.thread_launch_pref_repo.save_confirmed(
        owner_user_id,
        member_id,
        normalize_launch_config_payload(payload),
    )


def save_last_successful_config(app: Any, owner_user_id: str, member_id: str, payload: dict[str, Any]) -> None:
    app.state.thread_launch_pref_repo.save_successful(
        owner_user_id,
        member_id,
        normalize_launch_config_payload(payload),
    )


def resolve_default_config(app: Any, owner_user_id: str, member_id: str) -> dict[str, Any]:
    prefs = app.state.thread_launch_pref_repo.get(owner_user_id, member_id) or {}
    leases = sandbox_service.list_user_leases(owner_user_id)
    providers = [item for item in sandbox_service.available_sandbox_types() if item.get("available")]
    recipes = list_library("recipe", owner_user_id=owner_user_id, recipe_repo=app.state.recipe_repo)
    member_threads = app.state.thread_repo.list_by_member(member_id)

    # @@@thread-launch-default-precedence - prefer the last successful thread config, then the last confirmed draft,
    # and only then derive from current leases/providers. This keeps defaults tied to actual member usage first.
    successful = _validate_saved_config(
        prefs.get("last_successful"), leases=leases, providers=providers, recipes=recipes
    )
    if successful is not None:
        return {"source": "last_successful", "config": successful}

    confirmed = _validate_saved_config(prefs.get("last_confirmed"), leases=leases, providers=providers, recipes=recipes)
    if confirmed is not None:
        return {"source": "last_confirmed", "config": confirmed}

    return {
        "source": "derived",
        "config": _derive_default_config(
            member_threads=member_threads,
            leases=leases,
            providers=providers,
            recipes=recipes,
        ),
    }


def _validate_saved_config(
    payload: dict[str, Any] | None,
    *,
    leases: list[dict[str, Any]],
    providers: list[dict[str, Any]],
    recipes: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None

    config = normalize_launch_config_payload(payload)
    provider_names = {str(item["name"]) for item in providers}
    recipes_by_id = {
        str(item["id"]): item for item in recipes if item.get("available", True) and item.get("provider_type")
    }

    if config["create_mode"] == "existing":
        lease_id = config.get("lease_id")
        if not lease_id:
            return None
        lease = next((item for item in leases if item["lease_id"] == lease_id), None)
        if lease is None:
            return None
        return {
            "create_mode": "existing",
            "provider_config": lease["provider_name"],
            "recipe": lease.get("recipe"),
            "lease_id": lease["lease_id"],
            "model": config.get("model"),
            "workspace": lease.get("cwd"),
        }

    provider_config = config.get("provider_config")
    recipe = config.get("recipe")
    if not provider_config or provider_config not in provider_names or not isinstance(recipe, dict):
        return None
    provider_type = provider_type_from_name(provider_config)
    recipe_id = str(recipe.get("id") or "").strip()
    if not recipe_id or recipe_id not in recipes_by_id:
        return None
    if str(recipe.get("provider_type") or "") != provider_type:
        return None

    return {
        "create_mode": "new",
        "provider_config": provider_config,
        "recipe": recipe,
        "lease_id": None,
        "model": config.get("model"),
        "workspace": config.get("workspace"),
    }


def _derive_default_config(
    *,
    member_threads: list[dict[str, Any]],
    leases: list[dict[str, Any]],
    providers: list[dict[str, Any]],
    recipes: list[dict[str, Any]],
) -> dict[str, Any]:
    member_thread_ids = {str(item.get("id") or "").strip() for item in member_threads if item.get("id")}
    member_leases = [
        lease
        for lease in leases
        if any(str(thread_id or "").strip() in member_thread_ids for thread_id in lease.get("thread_ids") or [])
    ]
    if member_leases:
        lease = member_leases[0]
        return {
            "create_mode": "existing",
            "provider_config": lease["provider_name"],
            "recipe": lease.get("recipe"),
            "lease_id": lease["lease_id"],
            "model": None,
            "workspace": lease.get("cwd"),
        }

    provider_names = [str(item["name"]) for item in providers]
    provider_config = "local" if "local" in provider_names else (provider_names[0] if provider_names else "local")
    provider_type = provider_type_from_name(provider_config)
    recipe = next(
        (
            item
            for item in recipes
            if item.get("available", True) and str(item.get("provider_type") or "") == provider_type
        ),
        None,
    )
    return {
        "create_mode": "new",
        "provider_config": provider_config,
        "recipe": recipe,
        "lease_id": None,
        "model": None,
        "workspace": None,
    }
