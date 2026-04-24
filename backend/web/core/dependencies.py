import asyncio
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Request

from backend.identity.auth.dependencies import _get_auth_service as _get_auth_service
from backend.identity.auth.user_resolution import get_current_user as get_current_user
from backend.identity.auth.user_resolution import get_current_user_id as get_current_user_id
from backend.threads import convergence as thread_runtime_convergence
from backend.threads.activity_pool_service import get_or_create_agent
from backend.threads.sandbox_resolution import resolve_thread_sandbox
from sandbox.thread_context import set_current_thread_id


async def get_app(request: Request) -> FastAPI:
    return request.app


__all__ = [
    "get_app",
    "_get_auth_service",
    "get_current_user",
    "get_current_user_id",
    "verify_thread_owner",
    "verify_thread_row_owner",
    "get_thread_lock",
    "get_thread_agent",
]


async def verify_thread_owner(
    thread_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[FastAPI, Depends(get_app)],
) -> str:
    """Verify that user_id owns the thread. Returns user_id."""
    runtime_state = thread_runtime_convergence.inspect_owner_thread_runtime(app, thread_id)
    if runtime_state == "missing":
        raise HTTPException(404, "Thread not found")
    if runtime_state == "incomplete":
        raise HTTPException(409, "Thread runtime incomplete: missing workspace/sandbox binding")
    thread = app.state.thread_repo.get_by_id(thread_id)
    if not thread:
        raise HTTPException(404, "Thread not found")
    agent_user = app.state.user_repo.get_by_id(thread["agent_user_id"])
    if not agent_user or agent_user.owner_user_id != user_id:
        raise HTTPException(403, "Not authorized")
    return user_id


async def verify_thread_row_owner(
    thread_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[FastAPI, Depends(get_app)],
) -> str:
    """Verify ownership without mutating or converging thread runtime state."""
    thread = app.state.thread_repo.get_by_id(thread_id)
    if not thread:
        raise HTTPException(404, "Thread not found")
    agent_user = app.state.user_repo.get_by_id(thread["agent_user_id"])
    if not agent_user or agent_user.owner_user_id != user_id:
        raise HTTPException(403, "Not authorized")
    return user_id


async def get_thread_lock(app: Annotated[FastAPI, Depends(get_app)], thread_id: str) -> asyncio.Lock:
    """Get or create a lock for a specific thread."""
    async with app.state.thread_locks_guard:
        lock = app.state.thread_locks.get(thread_id)
        if lock is None:
            lock = asyncio.Lock()
            app.state.thread_locks[thread_id] = lock
        return lock


async def get_thread_agent(
    app: Annotated[FastAPI, Depends(get_app)],
    thread_id: str,
    require_remote: bool = False,
) -> Any:
    """Get or create agent for a thread, with optional remote sandbox requirement."""
    sandbox_type = resolve_thread_sandbox(app, thread_id)
    if require_remote and sandbox_type == "local":
        raise HTTPException(400, "Local threads have no remote sandbox")
    try:
        set_current_thread_id(thread_id)
        agent = await get_or_create_agent(app, sandbox_type, thread_id=thread_id)
    # @@@http_passthrough - keep intentional HTTP status from agent bootstrap
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(503, f"Sandbox agent init failed for {sandbox_type}: {e}") from e
    if not hasattr(agent, "_sandbox"):
        raise HTTPException(400, "Agent has no sandbox")
    if require_remote and agent._sandbox.name == "local":
        raise HTTPException(400, "Agent has no remote sandbox")
    return agent
