"""Resolve + persist per-agent new-thread config defaults."""

from __future__ import annotations

from typing import Any

from backend.web.services import sandbox_service
from backend.web.services.library_service import list_library
from sandbox.recipes import default_recipe_id, default_recipe_snapshot, normalize_recipe_snapshot, provider_type_from_name


def normalize_launch_config_payload(payload: dict[str, Any]) -> dict[str, Any]:
    create_mode = "existing" if payload.get("create_mode") == "existing" else "new"
    existing_sandbox_id = str(payload.get("existing_sandbox_id") or "").strip() or None
    if create_mode != "existing":
        existing_sandbox_id = None
    return {
        "create_mode": create_mode,
        "provider_config": str(payload.get("provider_config") or "").strip(),
        "sandbox_template_id": str(payload.get("sandbox_template_id") or "").strip() or None,
        "existing_sandbox_id": existing_sandbox_id,
        "model": str(payload.get("model") or "").strip() or None,
        "workspace": str(payload.get("workspace") or "").strip() or None,
    }


def build_new_launch_config(
    *,
    provider_config: str,
    sandbox_template_id: str | None,
    model: str | None,
    workspace: str | None,
) -> dict[str, Any]:
    return normalize_launch_config_payload(
        {
            "create_mode": "new",
            "provider_config": provider_config,
            "sandbox_template_id": sandbox_template_id,
            "existing_sandbox_id": None,
            "model": model,
            "workspace": workspace,
        }
    )


def resolve_default_config(app: Any, owner_user_id: str, agent_user_id: str) -> dict[str, Any]:
    providers = [item for item in sandbox_service.available_sandbox_types() if item.get("available")]
    sandbox_templates = list_library("sandbox-template", owner_user_id=owner_user_id, recipe_repo=app.state.recipe_repo)
    agent_threads = app.state.thread_repo.list_by_agent_user(agent_user_id)

    return {
        "source": "derived",
        "config": _derive_default_config(
            app=app,
            owner_user_id=owner_user_id,
            agent_threads=agent_threads,
            providers=providers,
            sandbox_templates=sandbox_templates,
        ),
    }


def _derive_default_config(
    *,
    app: Any,
    owner_user_id: str,
    agent_threads: list[dict[str, Any]],
    providers: list[dict[str, Any]],
    sandbox_templates: list[dict[str, Any]],
) -> dict[str, Any]:
    for thread in _iter_default_bridge_threads(agent_threads):
        # @@@workspace-bridge-read-precedence - launch-config resolves workspace-backed
        # existing-mode defaults from workspace+sandbox truth before considering new defaults.
        config = _resolve_workspace_backed_existing_config(
            app=app,
            current_workspace_id=thread["current_workspace_id"],
            owner_user_id=owner_user_id,
        )
        if config is not None:
            return config

    provider_names = [str(item["name"]) for item in providers]
    provider_config = "local" if "local" in provider_names else (provider_names[0] if provider_names else "local")
    sandbox_template = next(
        (item for item in sandbox_templates if item.get("available", True) and _sandbox_template_matches_provider(item, provider_config)),
        None,
    )
    sandbox_template_snapshot = (
        normalize_recipe_snapshot(
            provider_type_from_name(provider_config),
            sandbox_template,
            provider_name=provider_config,
        )
        if sandbox_template is not None
        else None
    )
    return {
        "create_mode": "new",
        "provider_config": provider_config,
        "sandbox_template_id": str(sandbox_template["id"]) if sandbox_template is not None else None,
        "sandbox_template": sandbox_template_snapshot,
        "existing_sandbox_id": None,
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


def _resolve_workspace_backed_existing_config(
    *,
    app: Any,
    current_workspace_id: str,
    owner_user_id: str,
) -> dict[str, Any] | None:
    workspace_repo = getattr(app.state, "workspace_repo", None)
    get_by_id = getattr(workspace_repo, "get_by_id", None)
    if callable(get_by_id):
        workspace = get_by_id(current_workspace_id)
        if workspace is not None:
            sandbox_id = _required_bridge_text(workspace, "sandbox_id", "workspace")
            workspace_owner_user_id = _required_bridge_text(workspace, "owner_user_id", "workspace")
            if workspace_owner_user_id != owner_user_id:
                raise PermissionError(f"workspace owner mismatch: expected {owner_user_id}, got {workspace_owner_user_id}")
            sandbox_repo = getattr(app.state, "sandbox_repo", None)
            sandbox_get_by_id = getattr(sandbox_repo, "get_by_id", None)
            if not callable(sandbox_get_by_id):
                raise RuntimeError("sandbox_repo must support get_by_id")
            sandbox = sandbox_get_by_id(sandbox_id)
            if sandbox is None:
                raise RuntimeError(f"sandbox not found: {sandbox_id}")
            sandbox_owner_user_id = _required_bridge_text(sandbox, "owner_user_id", "sandbox")
            if sandbox_owner_user_id != owner_user_id:
                raise PermissionError(f"sandbox owner mismatch: expected {owner_user_id}, got {sandbox_owner_user_id}")
            sandbox_template = _resolve_workspace_backed_sandbox_template(
                app=app,
                owner_user_id=owner_user_id,
                sandbox=sandbox,
            )
            return {
                "create_mode": "existing",
                "provider_config": _required_bridge_text(sandbox, "provider_name", "sandbox"),
                "sandbox_template": sandbox_template,
                "existing_sandbox_id": _required_bridge_text(sandbox, "id", "sandbox"),
                "model": None,
                "workspace": _required_bridge_text(workspace, "workspace_path", "workspace"),
            }
    return None


def _resolve_workspace_backed_sandbox_template(
    *,
    app: Any,
    owner_user_id: str,
    sandbox: Any,
) -> dict[str, Any]:
    sandbox_template_id = _required_bridge_text(sandbox, "sandbox_template_id", "sandbox")
    template_provider_name = str(sandbox_template_id.split(":", 1)[0]).strip()
    if not template_provider_name:
        raise RuntimeError("sandbox.sandbox_template_id must include provider name")

    if sandbox_template_id == default_recipe_id(template_provider_name):
        return default_recipe_snapshot(
            provider_type_from_name(template_provider_name),
            provider_name=template_provider_name,
        )

    recipe_repo = getattr(app.state, "recipe_repo", None)
    get = getattr(recipe_repo, "get", None)
    if not callable(get):
        raise RuntimeError("recipe_repo must support get")
    row = get(owner_user_id, sandbox_template_id)
    if row is None:
        raise RuntimeError(f"sandbox template not found: {sandbox_template_id}")
    data = row.get("data") if isinstance(row, dict) else getattr(row, "data", None)
    if not isinstance(data, dict):
        raise RuntimeError("sandbox template row data must be an object")
    provider_type = str(data.get("provider_type") or provider_type_from_name(template_provider_name)).strip()
    if not provider_type:
        raise RuntimeError("sandbox template provider_type is required")
    return normalize_recipe_snapshot(provider_type, data)


def _required_bridge_text(row: Any, key: str, label: str) -> str:
    value = row.get(key) if isinstance(row, dict) else getattr(row, key, None)
    if isinstance(value, str):
        value = value.strip()
    if value is None or value == "":
        raise RuntimeError(f"{label}.{key} is required")
    return str(value)


def _sandbox_template_matches_provider(sandbox_template: dict[str, Any], provider_config: str) -> bool:
    provider_name = str(sandbox_template.get("provider_name") or "").strip()
    if provider_name:
        return provider_name == provider_config
    provider_type = provider_type_from_name(provider_config)
    return str(sandbox_template.get("provider_type") or "") == provider_type
