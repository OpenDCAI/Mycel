"""Resolve + persist per-agent new-thread config defaults."""

from __future__ import annotations

from typing import Any

from backend.web.services import sandbox_service
from backend.web.services.library_service import list_library
from sandbox.recipes import normalize_recipe_snapshot, provider_type_from_name


def normalize_launch_config_payload(payload: dict[str, Any]) -> dict[str, Any]:
    create_mode = "existing" if payload.get("create_mode") == "existing" else "new"
    lease_id = str(payload.get("lease_id") or "").strip() or None
    if create_mode != "existing":
        lease_id = None
    return {
        "create_mode": create_mode,
        "provider_config": str(payload.get("provider_config") or "").strip(),
        "recipe_id": str(payload.get("recipe_id") or "").strip() or None,
        "lease_id": lease_id,
        "model": str(payload.get("model") or "").strip() or None,
        "workspace": str(payload.get("workspace") or "").strip() or None,
    }


def build_existing_launch_config(
    *,
    lease: dict[str, Any],
    model: str | None,
    workspace: str | None,
) -> dict[str, Any]:
    return normalize_launch_config_payload(
        {
            "create_mode": "existing",
            "provider_config": lease.get("provider_name"),
            "lease_id": lease.get("lease_id"),
            "model": model,
            "workspace": workspace,
        }
    )


def build_new_launch_config(
    *,
    provider_config: str,
    recipe_id: str | None,
    model: str | None,
    workspace: str | None,
) -> dict[str, Any]:
    return normalize_launch_config_payload(
        {
            "create_mode": "new",
            "provider_config": provider_config,
            "recipe_id": recipe_id,
            "lease_id": None,
            "model": model,
            "workspace": workspace,
        }
    )


def save_last_confirmed_config(app: Any, owner_user_id: str, agent_user_id: str, payload: dict[str, Any]) -> None:
    _save_launch_config(app.state.thread_launch_pref_repo.save_confirmed, owner_user_id, agent_user_id, payload)


def save_last_successful_config(app: Any, owner_user_id: str, agent_user_id: str, payload: dict[str, Any]) -> None:
    _save_launch_config(app.state.thread_launch_pref_repo.save_successful, owner_user_id, agent_user_id, payload)


def resolve_default_config(app: Any, owner_user_id: str, agent_user_id: str) -> dict[str, Any]:
    prefs = app.state.thread_launch_pref_repo.get(owner_user_id, agent_user_id) or {}
    leases = sandbox_service.list_user_leases(
        owner_user_id,
        thread_repo=app.state.thread_repo,
        user_repo=app.state.user_repo,
    )
    providers = [item for item in sandbox_service.available_sandbox_types() if item.get("available")]
    recipes = list_library("recipe", owner_user_id=owner_user_id, recipe_repo=app.state.recipe_repo)
    agent_threads = app.state.thread_repo.list_by_agent_user(agent_user_id)

    # @@@thread-launch-default-precedence - prefer the last successful thread config, then the last confirmed draft,
    # and only then derive from current leases/providers. This keeps defaults tied to actual agent usage first.
    successful = _validate_saved_config(prefs.get("last_successful"), leases=leases, providers=providers, recipes=recipes)
    if successful is not None:
        return {"source": "last_successful", "config": successful}

    confirmed = _validate_saved_config(prefs.get("last_confirmed"), leases=leases, providers=providers, recipes=recipes)
    if confirmed is not None:
        return {"source": "last_confirmed", "config": confirmed}

    return {
        "source": "derived",
        "config": _derive_default_config(
            agent_threads=agent_threads,
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
    recipes_by_id = {str(item["id"]): item for item in recipes if item.get("available", True) and item.get("provider_type")}

    if config["create_mode"] == "existing":
        lease_id = config.get("lease_id")
        if not lease_id:
            return None
        lease = next((item for item in leases if item["lease_id"] == lease_id), None)
        if lease is None:
            return None
        return _existing_config_from_lease(lease, model=config.get("model"), workspace=lease.get("cwd"))

    provider_config = config.get("provider_config")
    recipe_id = str(config.get("recipe_id") or "").strip()
    if not provider_config or provider_config not in provider_names or not recipe_id:
        return None
    if not recipe_id or recipe_id not in recipes_by_id:
        return None
    recipe = recipes_by_id[recipe_id]
    if not _recipe_matches_provider(recipe, provider_config):
        return None
    recipe_snapshot = normalize_recipe_snapshot(provider_type_from_name(provider_config), recipe, provider_name=provider_config)

    return {
        "create_mode": "new",
        "provider_config": provider_config,
        "recipe_id": recipe_id,
        "recipe": recipe_snapshot,
        "lease_id": None,
        "model": config.get("model"),
        "workspace": config.get("workspace"),
    }


def _save_launch_config(save_fn: Any, owner_user_id: str, agent_user_id: str, payload: dict[str, Any]) -> None:
    save_fn(
        owner_user_id,
        agent_user_id,
        normalize_launch_config_payload(payload),
    )


def _existing_config_from_lease(lease: dict[str, Any], *, model: str | None, workspace: str | None) -> dict[str, Any]:
    return {
        "create_mode": "existing",
        "provider_config": lease.get("provider_name"),
        "recipe": lease.get("recipe"),
        "lease_id": lease.get("lease_id"),
        "model": model,
        "workspace": workspace,
    }


def _derive_default_config(
    *,
    agent_threads: list[dict[str, Any]],
    leases: list[dict[str, Any]],
    providers: list[dict[str, Any]],
    recipes: list[dict[str, Any]],
) -> dict[str, Any]:
    leases_by_id = {str(lease.get("lease_id") or "").strip(): lease for lease in leases if str(lease.get("lease_id") or "").strip()}
    for thread in _iter_default_bridge_threads(agent_threads):
        lease = leases_by_id.get(thread["current_workspace_id"])
        if lease is not None:
            return _existing_config_from_lease(lease, model=None, workspace=lease.get("cwd"))

    provider_names = [str(item["name"]) for item in providers]
    provider_config = "local" if "local" in provider_names else (provider_names[0] if provider_names else "local")
    recipe = next(
        (item for item in recipes if item.get("available", True) and _recipe_matches_provider(item, provider_config)),
        None,
    )
    recipe_snapshot = (
        normalize_recipe_snapshot(provider_type_from_name(provider_config), recipe, provider_name=provider_config)
        if recipe is not None
        else None
    )
    return {
        "create_mode": "new",
        "provider_config": provider_config,
        "recipe_id": str(recipe["id"]) if recipe is not None else None,
        "recipe": recipe_snapshot,
        "lease_id": None,
        "model": None,
        "workspace": None,
    }


def _iter_default_bridge_threads(agent_threads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    threads_with_bridge = []
    for thread in agent_threads:
        current_workspace_id = str(thread.get("current_workspace_id") or "").strip()
        if current_workspace_id:
            threads_with_bridge.append({**thread, "current_workspace_id": current_workspace_id})

    # @@@launch-config-thread-bridge-authority - replay-15 makes thread-owned
    # current_workspace_id the discovery authority for derived existing-mode
    # defaults; live lease lookup only materializes that bridge.
    if threads_with_bridge and all(item.get("created_at") is not None for item in threads_with_bridge):
        return sorted(threads_with_bridge, key=lambda item: item["created_at"], reverse=True)
    return threads_with_bridge


def _recipe_matches_provider(recipe: dict[str, Any], provider_config: str) -> bool:
    provider_name = str(recipe.get("provider_name") or "").strip()
    if provider_name:
        return provider_name == provider_config
    provider_type = provider_type_from_name(provider_config)
    return str(recipe.get("provider_type") or "") == provider_type
