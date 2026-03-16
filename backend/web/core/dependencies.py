"""FastAPI dependency injection functions."""

import asyncio
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Request

from backend.web.services.agent_pool import get_or_create_agent, resolve_thread_sandbox
from sandbox.thread_context import set_current_thread_id


async def get_app(request: Request) -> FastAPI:
    """Get FastAPI app instance from request."""
    return request.app


async def get_current_member_id(request: Request) -> str:
    """Extract member_id from JWT Bearer token."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(401, "Missing or invalid Authorization header")
    token = auth_header[7:]
    auth_service = getattr(request.app.state, "auth_service", None)
    if auth_service is None:
        raise HTTPException(500, "Auth service not initialized")
    try:
        return auth_service.verify_token(token)
    except ValueError as e:
        raise HTTPException(401, str(e))


async def verify_thread_owner(
    thread_id: str,
    member_id: Annotated[str, Depends(get_current_member_id)],
    app: Annotated[FastAPI, Depends(get_app)],
) -> str:
    """Verify that member_id owns the thread. Returns member_id."""
    thread = app.state.thread_repo.get_by_id(thread_id)
    if not thread:
        raise HTTPException(404, "Thread not found")
    agent_member = app.state.member_repo.get_by_id(thread["member_id"])
    if not agent_member or agent_member.owner_id != member_id:
        raise HTTPException(403, "Not authorized")
    return member_id


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
