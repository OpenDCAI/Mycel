"""User settings management endpoints."""

import json
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from backend.web.core.dependencies import get_current_user_id
from config.models_loader import ModelsLoader
from config.models_schema import ModelsConfig

router = APIRouter(prefix="/api/settings", tags=["settings"])
CurrentUserId = Annotated[str, Depends(get_current_user_id)]


# ============================================================================
# User preferences (preferences.json)
# ============================================================================


class WorkspaceSettings(BaseModel):
    default_workspace: str | None = None
    recent_workspaces: list[str] = []
    default_model: str = "leon:large"


class WorkspaceRequest(BaseModel):
    workspace: str


class DirectoryItem(BaseModel):
    name: str
    path: str
    is_dir: bool


def _resolve_workspace_path_or_400(
    workspace: str,
    *,
    missing_detail: str,
    not_dir_detail: str,
) -> str:
    workspace_path = Path(workspace).expanduser().resolve()
    if not workspace_path.exists():
        raise HTTPException(status_code=400, detail=missing_detail)
    if not workspace_path.is_dir():
        raise HTTPException(status_code=400, detail=not_dir_detail)
    return str(workspace_path)


def _get_settings_repo(request: Request):
    repo = getattr(request.app.state, "user_settings_repo", None)
    if repo is None:
        raise RuntimeError("user_settings_repo is required for backend web settings routes")
    return repo


def _load_workspace_settings(repo: Any, user_id: str) -> WorkspaceSettings:
    row = repo.get(user_id)
    if row is None:
        return WorkspaceSettings()
    return WorkspaceSettings(
        default_workspace=row.get("default_workspace"),
        recent_workspaces=row.get("recent_workspaces") or [],
        default_model=row.get("default_model") or "leon:large",
    )


# ============================================================================
# Models config (models.json)
# ============================================================================


def _load_merged_models_for_storage(repo: Any, user_id: str) -> ModelsConfig:
    loader = ModelsLoader()
    # @@@repo-backed-model-merge - repo-backed user settings must override filesystem user models, but still preserve system defaults.
    system = loader._load_json(loader._system_dir / "models.json")
    merged = loader._merge(system, repo.get_models_config(user_id) or {})
    merged = loader._merge(merged, loader._load_project())
    merged = loader._expand_env_vars(merged)
    merged["catalog"] = system.get("catalog", [])
    merged["virtual_models"] = system.get("virtual_models", [])
    return ModelsConfig(**merged)


# ============================================================================
# Settings endpoint (returns workspace + models combined for frontend compat)
# ============================================================================


class ProviderConfig(BaseModel):
    api_key: str | None = None
    base_url: str | None = None


class UserSettings(BaseModel):
    """Combined settings for frontend compatibility."""

    default_workspace: str | None = None
    recent_workspaces: list[str] = []
    default_model: str = "leon:large"
    model_mapping: dict[str, str] = {}
    enabled_models: list[str] = []
    custom_models: list[str] = []
    custom_config: dict[str, dict[str, Any]] = {}
    providers: dict[str, ProviderConfig] = {}


@router.get("")
async def get_settings(request: Request, user_id: CurrentUserId) -> UserSettings:
    """Get combined settings for the authenticated user."""
    repo = _get_settings_repo(request)
    ws = _load_workspace_settings(repo, user_id)
    models = _load_merged_models_for_storage(repo, user_id)

    # Build compat view
    mapping = {k: v.model for k, v in models.mapping.items()}
    providers = {k: ProviderConfig(api_key=v.api_key, base_url=v.base_url) for k, v in models.providers.items()}
    raw = repo.get_models_config(user_id) or {}
    custom_config = raw.get("pool", {}).get("custom_config", {})

    return UserSettings(
        default_workspace=ws.default_workspace,
        recent_workspaces=ws.recent_workspaces,
        default_model=ws.default_model,
        model_mapping=mapping,
        enabled_models=models.pool.enabled,
        custom_models=models.pool.custom,
        custom_config=custom_config,
        providers=providers,
    )


@router.get("/browse")
async def browse_filesystem(path: str = Query(default="~"), include_files: bool = Query(default=False)) -> dict[str, Any]:
    """Browse filesystem directories (and optionally files)."""
    try:
        target_path = Path(path).expanduser().resolve()
        if not target_path.exists():
            raise HTTPException(status_code=404, detail="Path does not exist")
        if not target_path.is_dir():
            raise HTTPException(status_code=400, detail="Path is not a directory")

        parent = str(target_path.parent) if target_path.parent != target_path else None
        items: list[DirectoryItem] = []
        try:
            for item in sorted(target_path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
                if item.name.startswith("."):
                    continue
                if item.is_dir() or include_files:
                    items.append(DirectoryItem(name=item.name, path=str(item), is_dir=item.is_dir()))
        except PermissionError:
            pass

        return {"current_path": str(target_path), "parent_path": parent, "items": [item.model_dump() for item in items]}
    # @@@http_passthrough - preserve explicit user-facing status codes from validation branches
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/read")
async def read_local_file(path: str = Query(...)) -> dict[str, Any]:
    """Read a local file's content (for SandboxBrowser in resources page)."""
    _read_max_bytes = 100 * 1024
    try:
        target = Path(path).expanduser().resolve()
        if not target.exists():
            raise HTTPException(status_code=404, detail="File not found")
        if target.is_dir():
            raise HTTPException(status_code=400, detail="Path is a directory")
        raw = target.read_bytes()
        truncated = len(raw) > _read_max_bytes
        content = raw[:_read_max_bytes].decode(errors="replace")
        return {"path": str(target), "content": content, "truncated": truncated}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/workspace")
async def set_default_workspace(
    request: WorkspaceRequest,
    req: Request,
    user_id: CurrentUserId,
) -> dict[str, Any]:
    """Set default workspace path."""
    workspace_str = _resolve_workspace_path_or_400(
        request.workspace,
        missing_detail="Workspace path does not exist",
        not_dir_detail="Workspace path is not a directory",
    )

    repo = _get_settings_repo(req)
    repo.set_default_workspace(user_id, workspace_str)

    return {"success": True, "workspace": workspace_str}


@router.post("/workspace/recent")
async def add_recent_workspace(
    request: WorkspaceRequest,
    req: Request,
    user_id: CurrentUserId,
) -> dict[str, Any]:
    """Add a workspace to recent list."""
    workspace_str = _resolve_workspace_path_or_400(
        request.workspace,
        missing_detail="Invalid workspace path",
        not_dir_detail="Invalid workspace path",
    )

    repo = _get_settings_repo(req)
    repo.add_recent_workspace(user_id, workspace_str)

    return {"success": True}


class DefaultModelRequest(BaseModel):
    model: str


@router.post("/default-model")
async def set_default_model(
    request: DefaultModelRequest,
    req: Request,
    user_id: CurrentUserId,
) -> dict[str, Any]:
    """Set default virtual model preference."""
    repo = _get_settings_repo(req)
    repo.set_default_model(user_id, request.model)
    return {"success": True, "default_model": request.model}


# ============================================================================
# Model config hot-reload
# ============================================================================


class ModelConfigRequest(BaseModel):
    model: str
    thread_id: str | None = None


@router.post("/config")
async def update_model_config(request: ModelConfigRequest, req: Request) -> dict[str, Any]:
    """Update model configuration for agent (hot-reload) and persist per-thread."""
    from backend.web.services.agent_pool import update_agent_config

    # Persist model per-thread if thread_id provided
    if request.thread_id:
        thread_repo = getattr(req.app.state, "thread_repo", None)
        if thread_repo:
            thread_repo.update(request.thread_id, model=request.model)

    try:
        result = await update_agent_config(app_obj=req.app, model=request.model, thread_id=request.thread_id)
        # Always return the original requested model name, not the resolved one
        result["model"] = request.model
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update config: {str(e)}")


# ============================================================================
# Available models
# ============================================================================


@router.get("/available-models")
async def get_available_models(req: Request, user_id: CurrentUserId) -> dict[str, Any]:
    """Get all available models and virtual models from models.json."""
    models_file = Path(__file__).parent.parent.parent.parent / "core" / "runtime" / "middleware" / "monitor" / "models.json"

    if not models_file.exists():
        raise HTTPException(status_code=500, detail="Models data not found")

    try:
        with open(models_file, encoding="utf-8") as f:
            raw_data = json.load(f)

        # 解析 OpenRouter 原始格式 {"data": [{id, pricing, context_length, ...}]}
        bundled_providers: dict[str, str] = {}
        models_list = []
        seen: set[str] = set()
        for m in raw_data.get("data", []):
            model_id = m.get("id", "")
            if "/" not in model_id:
                continue
            provider, short_name = model_id.split("/", 1)
            if short_name in seen:
                continue
            seen.add(short_name)
            bundled_providers[short_name] = provider
            models_list.append(
                {
                    "id": short_name,
                    "name": m.get("name", short_name),
                    "provider": provider,
                    "context_length": m.get("context_length"),
                }
            )
        pricing_ids = seen

        # Merge custom + orphaned enabled models
        repo = _get_settings_repo(req)
        mc = _load_merged_models_for_storage(repo, user_id)
        data = repo.get_models_config(user_id) or {}
        custom_providers = data.get("pool", {}).get("custom_providers", {})
        extra_ids = set(mc.pool.custom) | (set(mc.pool.enabled) - pricing_ids)
        for mid in sorted(extra_ids):
            models_list.append(
                {
                    "id": mid,
                    "name": mid,
                    "custom": True,
                    "provider": custom_providers.get(mid) or bundled_providers.get(mid),
                }
            )

        # Virtual models from system defaults
        virtual_models = [vm.model_dump() for vm in mc.virtual_models]

        return {"models": models_list, "virtual_models": virtual_models}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load available models: {str(e)}")


# ============================================================================
# Model mapping
# ============================================================================


class ModelMappingRequest(BaseModel):
    mapping: dict[str, dict[str, Any]]


@router.post("/model-mapping")
async def update_model_mapping(
    request: ModelMappingRequest,
    req: Request,
    user_id: CurrentUserId,
) -> dict[str, Any]:
    """Update virtual model mapping → models config."""
    repo = _get_settings_repo(req)
    data = repo.get_models_config(user_id) or {}
    mapping = data.get("mapping", {})
    for name, spec in request.mapping.items():
        if isinstance(spec, dict):
            if name in mapping and isinstance(mapping[name], dict):
                mapping[name].update(spec)
            else:
                mapping[name] = spec
    data["mapping"] = mapping
    repo.set_models_config(user_id, data)
    return {"success": True, "model_mapping": request.mapping}


# ============================================================================
# Model pool (enable/disable, custom)
# ============================================================================


class ModelToggleRequest(BaseModel):
    model_id: str
    enabled: bool


@router.post("/models/toggle")
async def toggle_model(
    request: ModelToggleRequest,
    req: Request,
    user_id: CurrentUserId,
) -> dict[str, Any]:
    """Enable or disable a model."""
    repo = _get_settings_repo(req)
    data = repo.get_models_config(user_id) or {}
    pool = data.setdefault("pool", {"enabled": [], "custom": []})
    enabled = pool.setdefault("enabled", [])

    if request.enabled:
        if request.model_id not in enabled:
            enabled.append(request.model_id)
    else:
        if request.model_id in enabled:
            enabled.remove(request.model_id)

    repo.set_models_config(user_id, data)
    return {"success": True, "enabled_models": enabled}


class CustomModelRequest(BaseModel):
    model_id: str
    provider: str
    based_on: str | None = None
    context_limit: int | None = None


@router.post("/models/custom")
async def add_custom_model(
    request: CustomModelRequest,
    req: Request,
    user_id: CurrentUserId,
) -> dict[str, Any]:
    """Add a custom model + auto-enable."""
    repo = _get_settings_repo(req)
    data = repo.get_models_config(user_id) or {}
    pool = data.setdefault("pool", {"enabled": [], "custom": []})
    custom = pool.setdefault("custom", [])
    enabled = pool.setdefault("enabled", [])

    if request.model_id not in custom:
        custom.append(request.model_id)
    if request.model_id not in enabled:
        enabled.append(request.model_id)

    custom_providers = pool.setdefault("custom_providers", {})
    custom_providers[request.model_id] = request.provider

    # Store based_on/context_limit in custom_config
    if request.based_on or request.context_limit:
        custom_config = pool.setdefault("custom_config", {})
        cfg: dict[str, Any] = custom_config.get(request.model_id, {})
        if request.based_on:
            cfg["based_on"] = request.based_on
        if request.context_limit:
            cfg["context_limit"] = request.context_limit
        custom_config[request.model_id] = cfg

    repo.set_models_config(user_id, data)
    return {"success": True, "custom_models": custom, "enabled_models": enabled}


class ModelTestRequest(BaseModel):
    model_id: str


@router.post("/models/test")
async def test_model(request: ModelTestRequest, req: Request, user_id: CurrentUserId) -> dict[str, Any]:
    """Test if a model is reachable by sending a minimal request."""
    import asyncio

    repo = _get_settings_repo(req)
    mc = _load_merged_models_for_storage(repo, user_id)

    # Resolve virtual model
    resolved, overrides = mc.resolve_model(request.model_id)
    provider_name = overrides.get("model_provider") or (mc.active.provider if mc.active else None)

    # Check custom_providers mapping
    data = repo.get_models_config(user_id) or {}
    custom_providers = data.get("pool", {}).get("custom_providers", {})
    if request.model_id in custom_providers:
        provider_name = custom_providers[request.model_id]

    # Infer provider from model name if still unknown
    if not provider_name:
        from langchain.chat_models.base import _attempt_infer_model_provider

        provider_name = _attempt_infer_model_provider(resolved)

    # Get credentials from providers config
    p = mc.get_provider(provider_name) if provider_name else None

    try:
        from langchain.chat_models import init_chat_model

        from core.model_params import normalize_model_kwargs

        kwargs: dict[str, Any] = {}
        if provider_name:
            kwargs["model_provider"] = provider_name
        if p and p.api_key:
            kwargs["api_key"] = p.api_key
        if p and p.base_url:
            url = p.base_url.rstrip("/")
            if url.endswith("/v1"):
                url = url[:-3]
            if provider_name != "anthropic":
                url = f"{url}/v1"
            kwargs["base_url"] = url

        kwargs = normalize_model_kwargs(resolved, kwargs)
        model = init_chat_model(resolved, **kwargs)

        response = await asyncio.wait_for(model.ainvoke("hi"), timeout=15)
        content = response.content if hasattr(response, "content") else str(response)
        return {"success": True, "model": resolved, "response": content[:100]}
    except TimeoutError:
        return {"success": False, "error": "Request timed out (15s)"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.delete("/models/custom")
async def remove_custom_model(req: Request, user_id: CurrentUserId, model_id: str = Query(...)) -> dict[str, Any]:
    """Remove a custom model."""
    repo = _get_settings_repo(req)
    data = repo.get_models_config(user_id) or {}
    pool = data.setdefault("pool", {"enabled": [], "custom": []})
    custom = pool.setdefault("custom", [])
    enabled = pool.setdefault("enabled", [])

    if model_id in custom:
        custom.remove(model_id)
    if model_id in enabled:
        enabled.remove(model_id)

    # Clean up custom_providers and custom_config
    custom_providers = pool.get("custom_providers", {})
    custom_providers.pop(model_id, None)
    custom_config = pool.get("custom_config", {})
    custom_config.pop(model_id, None)

    repo.set_models_config(user_id, data)
    return {"success": True, "custom_models": custom}


class CustomModelConfigRequest(BaseModel):
    model_id: str
    based_on: str | None = None
    context_limit: int | None = None
    provider: str | None = None


@router.post("/models/custom/config")
async def update_custom_model_config(request: CustomModelConfigRequest, req: Request, user_id: CurrentUserId) -> dict[str, Any]:
    """Update based_on/context_limit/provider for a custom model."""
    repo = _get_settings_repo(req)
    data = repo.get_models_config(user_id) or {}
    pool = data.setdefault("pool", {})
    custom_config = pool.setdefault("custom_config", {})
    cfg: dict[str, Any] = custom_config.get(request.model_id, {})
    if request.based_on is not None:
        cfg["based_on"] = request.based_on or None
    if request.context_limit is not None:
        cfg["context_limit"] = request.context_limit or None
    custom_config[request.model_id] = cfg
    if request.provider:
        custom_providers = pool.setdefault("custom_providers", {})
        custom_providers[request.model_id] = request.provider
    repo.set_models_config(user_id, data)
    return {"success": True, "custom_config": custom_config}


# ============================================================================
# Providers
# ============================================================================


class ProviderRequest(BaseModel):
    provider: str
    api_key: str | None = None
    base_url: str | None = None


@router.post("/providers")
async def update_provider(
    request: ProviderRequest,
    req: Request,
    user_id: CurrentUserId,
) -> dict[str, Any]:
    """Update provider config, then reload all agents."""
    repo = _get_settings_repo(req)
    data = repo.get_models_config(user_id) or {}
    providers = data.setdefault("providers", {})
    provider_data: dict[str, Any] = {}
    if request.api_key is not None:
        provider_data["api_key"] = request.api_key
    if request.base_url is not None:
        provider_data["base_url"] = request.base_url
    providers[request.provider] = provider_data
    repo.set_models_config(user_id, data)

    # @@@reload-agents-on-key-change — hot-reload all cached agents so they pick up new API keys
    pool = getattr(req.app.state, "agent_pool", {})
    reloaded = 0
    for agent in pool.values():
        agent.update_config()
        reloaded += 1

    return {"success": True, "provider": request.provider, "agents_reloaded": reloaded}


# ============================================================================
# Observation provider (observation.json)
# ============================================================================


class ObservationRequest(BaseModel):
    active: str | None = None
    langfuse: dict | None = None
    langsmith: dict | None = None


@router.get("/observation")
async def get_observation_settings(req: Request, user_id: CurrentUserId) -> dict[str, Any]:
    """Get observation provider configuration."""
    repo = _get_settings_repo(req)
    data = repo.get_observation_config(user_id)
    if data is not None:
        return data
    from config.observation_loader import ObservationLoader

    config = ObservationLoader().load()
    return config.model_dump()


@router.post("/observation")
async def update_observation_settings(request: ObservationRequest, req: Request, user_id: CurrentUserId) -> dict[str, Any]:
    """Update observation provider config.

    New threads will pick up the active provider at creation time.
    Existing threads keep their locked provider — only credentials are read live.
    """
    repo = _get_settings_repo(req)
    data = repo.get_observation_config(user_id) or {}

    data["active"] = request.active
    if request.langfuse is not None:
        existing = data.get("langfuse", {})
        existing.update(request.langfuse)
        data["langfuse"] = existing
    if request.langsmith is not None:
        existing = data.get("langsmith", {})
        existing.update(request.langsmith)
        data["langsmith"] = existing

    repo.set_observation_config(user_id, data)

    return {"success": True, "active": data.get("active")}


@router.get("/observation/verify")
async def verify_observation() -> dict[str, Any]:
    """Verify observation provider by querying recent traces via SDK."""
    from config.observation_loader import ObservationLoader

    config = ObservationLoader().load()

    if not config.active:
        return {"success": False, "error": "No active observation provider"}

    if config.active == "langfuse":
        cfg = config.langfuse
        if not cfg.secret_key or not cfg.public_key:
            return {"success": False, "error": "Langfuse keys not configured"}
        try:
            from langfuse.api.client import FernLangfuse

            client = FernLangfuse(
                username=cfg.public_key,
                password=cfg.secret_key,
                base_url=cfg.host or "https://cloud.langfuse.com",
            )
            traces = client.trace.list(limit=5)
            trace_list = [
                {"id": t.id, "name": t.name, "timestamp": str(t.timestamp)} for t in (traces.data if hasattr(traces, "data") else [])
            ]
            return {
                "success": True,
                "provider": "langfuse",
                "record_type": "trace",
                "records": trace_list,
                "traces": trace_list,
            }
        except Exception as e:
            return {"success": False, "provider": "langfuse", "error": str(e)}

    if config.active == "langsmith":
        cfg = config.langsmith
        if not cfg.api_key:
            return {"success": False, "error": "LangSmith API key not configured"}
        try:
            from langsmith import Client

            client = Client(
                api_key=cfg.api_key,
                api_url=cfg.endpoint or "https://api.smith.langchain.com",
            )
            runs = list(
                client.list_runs(
                    project_name=cfg.project or "default",
                    limit=5,
                )
            )
            run_list = [{"id": str(r.id), "name": r.name, "start_time": str(r.start_time)} for r in runs]
            return {
                "success": True,
                "provider": "langsmith",
                "record_type": "run",
                "records": run_list,
                "traces": run_list,
            }
        except Exception as e:
            return {"success": False, "provider": "langsmith", "error": str(e)}

    return {"success": False, "error": f"Unknown provider: {config.active}"}


class SandboxConfigRequest(BaseModel):
    name: str
    config: dict


@router.get("/sandboxes")
async def list_sandbox_configs(req: Request, user_id: CurrentUserId) -> dict[str, Any]:
    """List all sandbox configurations."""
    repo = _get_settings_repo(req)
    return {"sandboxes": repo.get_sandbox_configs(user_id) or {}}


@router.post("/sandboxes")
async def save_sandbox_config(request: SandboxConfigRequest, req: Request, user_id: CurrentUserId) -> dict[str, Any]:
    """Save a sandbox configuration."""
    from sandbox.config import SandboxConfig

    try:
        cfg = SandboxConfig(**request.config)
        repo = _get_settings_repo(req)
        existing = repo.get_sandbox_configs(user_id) or {}
        existing[request.name] = cfg.model_dump()
        repo.set_sandbox_configs(user_id, existing)
        return {"success": True, "path": f"supabase://user_settings/{user_id}/sandbox_configs/{request.name}"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
