"""Agent pool management service."""

import asyncio
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from core.runtime.agent import create_leon_agent
from storage.runtime import build_storage_container
from sandbox.manager import lookup_sandbox_for_thread
from sandbox.thread_context import set_current_thread_id
from core.identity.agent_registry import get_or_create_agent_id

# Thread lock for config updates
_config_update_locks: dict[str, asyncio.Lock] = {}


def create_agent_sync(sandbox_name: str, workspace_root: Path | None = None, model_name: str | None = None, agent: str | None = None, queue_manager: Any = None) -> Any:
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
        queue_manager=queue_manager,
        verbose=True,
        agent=agent,
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

    # For local sandbox, check if thread has custom cwd (memory → SQLite fallback)
    workspace_root = None
    from backend.web.utils.helpers import load_thread_config

    thread_config = load_thread_config(thread_id)
    if sandbox_type == "local":
        cwd = app_obj.state.thread_cwd.get(thread_id)
        if not cwd and thread_config and thread_config.cwd:
            cwd = thread_config.cwd
            app_obj.state.thread_cwd[thread_id] = cwd
        if cwd:
            workspace_root = Path(cwd).resolve()

    # Look up model for this thread (thread config → preferences default)
    model_name = thread_config.model if thread_config and thread_config.model else None
    if not model_name:
        from backend.web.routers.settings import load_settings as load_preferences

        prefs = load_preferences()
        model_name = prefs.default_model

    # @@@agent-vs-member - thread_config.agent stores a member ID (e.g. "__leon__") for display,
    # NOT an agent type name ("bash", "general", etc.). Never pass it to create_leon_agent.
    agent_name = agent  # explicit caller-provided type only; None → default Leon agent

    # @@@ agent-init-thread - LeonAgent.__init__ uses run_until_complete, must run in thread
    qm = getattr(app_obj.state, "queue_manager", None)
    agent_obj = await asyncio.to_thread(create_agent_sync, sandbox_type, workspace_root, model_name, agent_name, qm)
    member = agent_name or "leon"
    agent_id = get_or_create_agent_id(
        member=member,
        thread_id=thread_id,
        sandbox_type=sandbox_type,
    )
    agent_obj.agent_id = agent_id
    pool[pool_key] = agent_obj
    return agent_obj


def resolve_thread_sandbox(app_obj: FastAPI, thread_id: str) -> str:
    """Look up sandbox type for a thread: memory cache → SQLite → sandbox DB → default 'local'."""
    mapping = app_obj.state.thread_sandbox
    if thread_id in mapping:
        return mapping[thread_id]
    from backend.web.utils.helpers import load_thread_config

    tc = load_thread_config(thread_id)
    if tc:
        mapping[thread_id] = tc.sandbox_type
        if tc.cwd:
            app_obj.state.thread_cwd.setdefault(thread_id, tc.cwd)
        return tc.sandbox_type
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
