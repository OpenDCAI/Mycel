"""Thread runtime pool lifecycle helpers."""

import asyncio
import logging
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from backend.thread_runtime.pool.factory import create_agent_sync
from backend.thread_runtime.sandbox import resolve_thread_sandbox
from backend.web.services.file_channel_service import get_file_channel_binding
from core.identity.agent_registry import get_or_create_agent_id
from sandbox.thread_context import set_current_thread_id

logger = logging.getLogger(__name__)

# Thread lock for config updates
_config_update_locks: dict[str, asyncio.Lock] = {}
_agent_create_locks: dict[str, asyncio.Lock] = {}


async def get_or_create_agent(app_obj: FastAPI, sandbox_type: str, thread_id: str | None = None, agent: str | None = None) -> Any:
    """Lazy agent pool — one agent per thread, created on demand."""
    if thread_id:
        set_current_thread_id(thread_id)

    # Per-thread Agent instance: pool key = thread_id:sandbox_type
    # This ensures complete isolation of middleware state (memory, todo, runtime, filesystem, etc.)
    if not thread_id:
        raise ValueError("thread_id is required for agent creation")

    pool_key = f"{thread_id}:{sandbox_type}"
    pool = app_obj.state.agent_pool
    if pool_key in pool:
        return pool[pool_key]

    # @@@agent-create-lock - first-hit thread loads can race between /runtime and /messages.
    # Serialize creation per pool key so a new thread gets exactly one LeonAgent instance.
    create_lock = _agent_create_locks.setdefault(pool_key, asyncio.Lock())
    async with create_lock:
        if pool_key in pool:
            return pool[pool_key]

        # For local sandbox, check if thread has custom cwd (live map -> persisted thread row).
        workspace_root = None
        thread_data = app_obj.state.thread_repo.get_by_id(thread_id) if hasattr(app_obj.state, "thread_repo") else None
        if sandbox_type == "local":
            cwd = app_obj.state.thread_cwd.get(thread_id)
            cwd_from_live_map = cwd is not None
            if not cwd and thread_data and thread_data.get("cwd"):
                cwd = thread_data["cwd"]
            if cwd:
                path = Path(cwd).expanduser()
                # @@@fresh-local-cwd-owns-workspace - a cwd chosen in this live backend session is
                # the caller contract for local threads; create it instead of silently falling
                # using the repo root. Persisted paths from another host stay advisory.
                if cwd_from_live_map:
                    path.mkdir(parents=True, exist_ok=True)
                    workspace_root = path.resolve()
                    app_obj.state.thread_cwd[thread_id] = str(workspace_root)
                # @@@host-local-cwd-is-advisory - persisted local thread cwd can come from another
                # host (for example a macOS path stored in shared Supabase but replayed inside a
                # Linux deployment container). Only pin workspace_root when that path exists here.
                elif path.exists() and path.is_dir():
                    workspace_root = path.resolve()
                    app_obj.state.thread_cwd[thread_id] = str(workspace_root)
                else:
                    app_obj.state.thread_cwd.pop(thread_id, None)
                    logger.warning("Ignoring unavailable local cwd for thread %s: %s", thread_id, cwd)

        user_repo = getattr(app_obj.state, "user_repo", None)
        agent_user_id = thread_data.get("agent_user_id") if thread_data else None
        agent_user = user_repo.get_by_id(agent_user_id) if agent_user_id and user_repo is not None else None

        # Look up model for this thread (thread override -> repo-backed user settings)
        model_name = thread_data.get("model") if thread_data else None
        models_config_override = None
        user_settings_repo = getattr(app_obj.state, "user_settings_repo", None)
        owner_user_id = getattr(agent_user, "owner_user_id", None) if agent_user is not None else None
        if user_settings_repo is not None and owner_user_id is not None:
            settings_row = user_settings_repo.get(owner_user_id) or {}
            if not model_name:
                model_name = settings_row.get("default_model")
            get_models_config = getattr(user_settings_repo, "get_models_config", None)
            if get_models_config is not None:
                models_config_override = get_models_config(owner_user_id)

        # @@@agent-vs-agent-user - thread row agent_user_id resolves an agent user for display,
        # NOT an agent type name ("bash", "general", etc.). Never pass it to create_leon_agent.
        agent_name = agent  # explicit caller-provided type only; None -> default Leon agent
        bundle_dir = None
        agent_config_id = None
        memory_config_override = None
        agent_config_repo = getattr(app_obj.state, "agent_config_repo", None)
        if thread_data and thread_data.get("agent_user_id"):
            if user_repo is None:
                raise RuntimeError(f"user_repo is required to resolve agent_config_id for thread {thread_id}")
            agent_user = agent_user or user_repo.get_by_id(thread_data["agent_user_id"])
            if agent_user is None or getattr(agent_user, "agent_config_id", None) is None:
                raise RuntimeError(f"thread.agent_user_id is missing agent_config_id for runtime startup: {thread_id}")
            agent_config_id = agent_user.agent_config_id
            if agent_config_repo is None:
                raise RuntimeError(f"agent_config_repo is required to resolve runtime config for thread {thread_id}")
            agent_config = agent_config_repo.get_config(agent_config_id)
            if agent_config is None:
                raise RuntimeError(f"Agent config {agent_config_id} is missing for runtime startup: {thread_id}")
            raw_compact = agent_config.get("compact")
            if raw_compact is not None and not isinstance(raw_compact, dict):
                raise RuntimeError(f"agent config compact must be a JSON object for runtime startup: {agent_config_id}")
            if raw_compact is not None:
                memory_config_override = {"compaction": raw_compact}

        # @@@chat-repos - construct chat_repos for ChatToolService (v2 messaging)
        chat_repos = None
        if user_repo is not None and thread_data:
            if not agent_user_id:
                raise RuntimeError(f"thread.agent_user_id is required for agent chat identity: {thread_id}")
            agent_user = agent_user or user_repo.get_by_id(agent_user_id)
            # @@@thread-chat-identity-source - agent users are now the stable social
            # identity root. Runtime threads no longer carry a second dedicated user_id.
            owner_id = agent_user.owner_user_id or ""
            chat_repos = {
                "chat_identity_id": agent_user_id,
                "owner_id": owner_id,
                "user_repo": user_repo,
                "messaging_service": getattr(app_obj.state, "messaging_service", None),
                "agent_config_repo": getattr(app_obj.state, "agent_config_repo", None),
            }

        try:
            binding = get_file_channel_binding(thread_id)
            if sandbox_type == "local" and binding.local_staging_root is not None:
                extra_allowed_paths: list[str] = [str(binding.local_staging_root)]
            else:
                extra_allowed_paths = []
        except Exception:
            extra_allowed_paths = []

        # Merge user-configured allowed_paths from sandbox config
        from sandbox.config import SandboxConfig

        try:
            sandbox_config = SandboxConfig.load(sandbox_type)
            extra_allowed_paths.extend(sandbox_config.allowed_paths)
        except FileNotFoundError:
            pass

        extra_allowed_paths_or_none: list[str] | None = extra_allowed_paths or None

        # @@@ agent-init-thread - LeonAgent.__init__ uses run_until_complete, must run in thread
        qm = getattr(app_obj.state, "queue_manager", None)
        create_kwargs = {
            "sandbox_name": sandbox_type,
            "workspace_root": workspace_root,
            "model_name": model_name,
            "agent": agent_name,
            "bundle_dir": bundle_dir,
            "thread_repo": getattr(app_obj.state, "thread_repo", None),
            "user_repo": getattr(app_obj.state, "user_repo", None),
            "queue_manager": qm,
            "chat_repos": chat_repos,
            "extra_allowed_paths": extra_allowed_paths_or_none,
            "web_app": app_obj,
        }
        if models_config_override is not None:
            create_kwargs["models_config_override"] = models_config_override
        if memory_config_override is not None:
            create_kwargs["memory_config_override"] = memory_config_override
        if agent_config_id is not None:
            create_kwargs["agent_config_id"] = agent_config_id
            create_kwargs["agent_config_repo"] = agent_config_repo
        agent_obj = await asyncio.to_thread(create_agent_sync, **create_kwargs)
        agent_identity_user_id = str(thread_data.get("agent_user_id") or "").strip() if thread_data else ""
        if not agent_identity_user_id:
            agent_identity_user_id = agent_name or "leon"
        agent_id = get_or_create_agent_id(
            user_id=agent_identity_user_id,
            thread_id=thread_id,
            sandbox_type=sandbox_type,
        )
        agent_obj.agent_id = agent_id

        # @@@per-thread-bind-mounts - inject bind_mounts into sandbox manager if configured
        bind_mounts = thread_data.get("bind_mounts") if thread_data else None
        if bind_mounts and hasattr(agent_obj, "_sandbox"):
            manager = getattr(agent_obj._sandbox, "_manager", None) or getattr(agent_obj._sandbox, "manager", None)
            if manager and hasattr(manager, "set_thread_bind_mounts"):
                manager.set_thread_bind_mounts(thread_id, bind_mounts)
        pool[pool_key] = agent_obj
        return agent_obj


async def update_agent_config(app_obj: FastAPI, model: str, thread_id: str | None = None) -> dict[str, Any]:
    """Update agent configuration with hot-reload."""
    lock_key = thread_id or "global"
    lock = _config_update_locks.setdefault(lock_key, asyncio.Lock())

    async with lock:
        if thread_id:
            sandbox_type = resolve_thread_sandbox(app_obj, thread_id)
            pool_key = f"{thread_id}:{sandbox_type}"
            pool = app_obj.state.agent_pool

            if pool_key not in pool:
                raise ValueError(f"Agent not found for thread {thread_id}")

            agent = pool[pool_key]

            try:
                await asyncio.to_thread(agent.update_config, model=model)
            except Exception as e:
                raise ValueError(f"Failed to update model config: {str(e)}")

            return {
                "success": True,
                "thread_id": thread_id,
                "model": agent.model_name,
                "message": f"Model updated to {agent.model_name}",
            }

        pool = app_obj.state.agent_pool
        updated_count = 0
        errors = []

        for pool_key, agent in pool.items():
            try:
                await asyncio.to_thread(agent.update_config, model=model)
                updated_count += 1
            except Exception as e:
                errors.append(f"{pool_key}: {str(e)}")

        if errors:
            raise ValueError(f"Failed to update some agents: {'; '.join(errors)}")

        return {
            "success": True,
            "updated_count": updated_count,
            "model": model,
            "message": f"Updated {updated_count} agent(s) to model {model}",
        }
