"""Agent pool management service."""

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from config.user_paths import preferred_existing_user_home_path
from core.identity.agent_registry import get_or_create_agent_id
from core.runtime.agent import create_leon_agent
from sandbox.manager import lookup_sandbox_for_thread
from sandbox.thread_context import set_current_thread_id
from storage.runtime import build_storage_container

logger = logging.getLogger(__name__)

# Thread lock for config updates
_config_update_locks: dict[str, asyncio.Lock] = {}
_agent_create_locks: dict[str, asyncio.Lock] = {}


def create_agent_sync(
    sandbox_name: str,
    workspace_root: Path | None = None,
    model_name: str | None = None,
    agent: str | None = None,
    bundle_dir: Path | None = None,
    thread_repo: Any = None,
    entity_repo: Any = None,
    member_repo: Any = None,
    queue_manager: Any = None,
    chat_repos: dict | None = None,
    extra_allowed_paths: list[str] | None = None,
    web_app: Any = None,
) -> Any:
    """Create a LeonAgent with the given sandbox. Runs in a thread."""
    storage_container = build_storage_container(
        main_db_path=os.getenv("LEON_DB_PATH"),
        eval_db_path=os.getenv("LEON_EVAL_DB_PATH"),
    )
    # @@@web-file-ops-repo - inject storage-backed repo so file_operations route to correct provider.
    from core.operations import FileOperationRecorder, set_recorder

    set_recorder(FileOperationRecorder(repo=storage_container.file_operation_repo()))
    return create_leon_agent(
        model_name=model_name,
        workspace_root=workspace_root or Path.cwd(),
        sandbox=sandbox_name if sandbox_name != "local" else None,
        storage_container=storage_container,
        permission_resolver_scope="thread",
        thread_repo=thread_repo,
        entity_repo=entity_repo,
        member_repo=member_repo,
        queue_manager=queue_manager,
        chat_repos=chat_repos,
        web_app=web_app,
        verbose=True,
        agent=agent,
        bundle_dir=bundle_dir,
        extra_allowed_paths=extra_allowed_paths,
    )


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

        # For local sandbox, check if thread has custom cwd (memory → SQLite fallback)
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
                # back to the repo root. Persisted paths from another host stay advisory.
                if cwd_from_live_map:
                    path.mkdir(parents=True, exist_ok=True)
                    workspace_root = path.resolve()
                    app_obj.state.thread_cwd[thread_id] = str(workspace_root)
                # @@@host-local-cwd-is-advisory - persisted local thread cwd can come from another
                # host (for example a macOS path stored in shared Supabase but replayed inside a
                # Linux staging container). Only pin workspace_root when that path exists here.
                elif path.exists() and path.is_dir():
                    workspace_root = path.resolve()
                    app_obj.state.thread_cwd[thread_id] = str(workspace_root)
                else:
                    app_obj.state.thread_cwd.pop(thread_id, None)
                    logger.warning("Ignoring unavailable local cwd for thread %s: %s", thread_id, cwd)

        # Look up model for this thread (threads table → preferences default)
        model_name = thread_data.get("model") if thread_data else None
        if not model_name:
            from backend.web.routers.settings import load_settings as load_preferences

            prefs = load_preferences()
            model_name = prefs.default_model

        # @@@agent-vs-member - thread_config.agent stores a member ID (e.g. "__leon__") for display,
        # NOT an agent type name ("bash", "general", etc.). Never pass it to create_leon_agent.
        agent_name = agent  # explicit caller-provided type only; None → default Leon agent
        bundle_dir = None
        if thread_data and thread_data.get("member_id"):
            member_dir = preferred_existing_user_home_path("members", str(thread_data["member_id"]))
            if member_dir.is_dir():
                bundle_dir = member_dir.resolve()

        # @@@chat-repos - construct chat_repos for ChatToolService if entity system is available
        chat_repos = None
        if hasattr(app_obj.state, "entity_repo") and thread_data:
            entity_repo = app_obj.state.entity_repo
            member_repo = getattr(app_obj.state, "member_repo", None)
            # Entity id = member_id in the new model; look up by member_id, not thread_id
            agent_member_id = thread_data.get("member_id")
            agent_entity = entity_repo.get_by_id(agent_member_id) if agent_member_id else None
            if agent_entity:
                # agent social identity = member_id
                agent_member = member_repo.get_by_id(agent_entity.member_id) if member_repo else None
                # owner social identity = owner's user_id (same as their member_id for humans)
                owner_user_id = agent_member.owner_user_id if agent_member else ""
                chat_repos = {
                    "user_id": agent_entity.member_id,  # agent's social identity = member_id
                    "owner_user_id": owner_user_id,
                    "entity_repo": entity_repo,
                    "chat_service": getattr(app_obj.state, "chat_service", None),
                    "chat_entity_repo": getattr(app_obj.state, "chat_entity_repo", None),
                    "chat_message_repo": getattr(app_obj.state, "chat_message_repo", None),
                    "member_repo": member_repo,
                    "chat_event_bus": getattr(app_obj.state, "chat_event_bus", None),
                }

        # @@@per-thread-file-access - ensure thread files are accessible from agent
        from backend.web.services.file_channel_service import get_file_channel_source

        try:
            source = get_file_channel_source(thread_id)
            extra_allowed_paths: list[str] = [str(source.host_path)] if sandbox_type == "local" else []
        except ValueError:
            extra_allowed_paths: list[str] = []

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
        agent_obj = await asyncio.to_thread(
            create_agent_sync,
            sandbox_name=sandbox_type,
            workspace_root=workspace_root,
            model_name=model_name,
            agent=agent_name,
            bundle_dir=bundle_dir,
            thread_repo=getattr(app_obj.state, "thread_repo", None),
            entity_repo=getattr(app_obj.state, "entity_repo", None),
            member_repo=getattr(app_obj.state, "member_repo", None),
            queue_manager=qm,
            chat_repos=chat_repos,
            extra_allowed_paths=extra_allowed_paths_or_none,
            web_app=app_obj,
        )
        member = agent_name or "leon"
        agent_id = get_or_create_agent_id(
            member=member,
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


def resolve_thread_sandbox(app_obj: FastAPI, thread_id: str) -> str:
    """Look up sandbox type for a thread: memory cache → SQLite → sandbox DB → default 'local'."""
    mapping = app_obj.state.thread_sandbox
    if thread_id in mapping:
        return mapping[thread_id]
    thread_data = app_obj.state.thread_repo.get_by_id(thread_id) if hasattr(app_obj.state, "thread_repo") else None
    if thread_data:
        mapping[thread_id] = thread_data.get("sandbox_type", "local")
        if thread_data.get("cwd"):
            app_obj.state.thread_cwd.setdefault(thread_id, thread_data["cwd"])
        return thread_data.get("sandbox_type", "local")
    detected = lookup_sandbox_for_thread(thread_id)
    if detected:
        mapping[thread_id] = detected
        return detected
    return "local"


async def update_agent_config(app_obj: FastAPI, model: str, thread_id: str | None = None) -> dict[str, Any]:
    """Update agent configuration with hot-reload.

    Args:
        app_obj: FastAPI application instance
        model: New model name (supports leon:* virtual names)
        thread_id: Optional thread ID to update specific agent

    Returns:
        Dict with success status and current config

    Raises:
        ValueError: If model validation fails or agent not found
    """
    # Get or create lock for this thread
    lock_key = thread_id or "global"
    if lock_key not in _config_update_locks:
        _config_update_locks[lock_key] = asyncio.Lock()

    async with _config_update_locks[lock_key]:
        if thread_id:
            # Update specific thread's agent
            sandbox_type = resolve_thread_sandbox(app_obj, thread_id)
            pool_key = f"{thread_id}:{sandbox_type}"
            pool = app_obj.state.agent_pool

            if pool_key not in pool:
                raise ValueError(f"Agent not found for thread {thread_id}")

            agent = pool[pool_key]

            # Validate model before applying
            try:
                # Run update_config in thread (it's synchronous)
                await asyncio.to_thread(agent.update_config, model=model)
            except Exception as e:
                raise ValueError(f"Failed to update model config: {str(e)}")

            return {
                "success": True,
                "thread_id": thread_id,
                "model": agent.model_name,
                "message": f"Model updated to {agent.model_name}",
            }
        else:
            # Global update: update all existing agents
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
