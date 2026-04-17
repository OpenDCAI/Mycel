"""FastAPI dependency injection functions."""

import asyncio
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Request

from backend.web.services.agent_pool import get_or_create_agent, resolve_thread_sandbox
from backend.web.services.thread_runtime_convergence import inspect_owner_thread_runtime
from sandbox.thread_context import set_current_thread_id


async def get_app(request: Request) -> FastAPI:
    """Get FastAPI app instance from request."""
    return request.app


def _get_auth_service(app: FastAPI):
    """Get auth service from app state, or raise 500."""
    auth_service = getattr(app.state, "auth_service", None)
    if auth_service is None:
        raise HTTPException(500, "Auth service not initialized")
    return auth_service


def _extract_jwt_payload(request: Request) -> dict:
    """Extract and verify JWT payload from Bearer token. Returns {user_id}."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(401, "Missing or invalid Authorization header")
    token = auth_header[7:]
    try:
        return _get_auth_service(request.app).verify_token(token)
    except ValueError as e:
        raise HTTPException(401, str(e))


async def _get_user_row_for_auth(request: Request, user_id: str, user_repo: Any) -> Any:
    state = request.app.state
    guard = getattr(state, "_auth_user_check_guard", None)
    if guard is None:
        guard = asyncio.Lock()
        setattr(state, "_auth_user_check_guard", guard)
    inflight = getattr(state, "_auth_user_check_inflight", None)
    if inflight is None:
        inflight = {}
        setattr(state, "_auth_user_check_inflight", inflight)

    async with guard:
        task = inflight.get(user_id)
        owns_task = task is None
        if task is None:
            # @@@auth-user-check-singleflight - Login fan-out starts many
            # authenticated requests at once; coalesce the same user existence
            # check without caching the result after this burst.
            task = asyncio.create_task(asyncio.to_thread(user_repo.get_by_id, user_id))
            inflight[user_id] = task

    try:
        return await task
    finally:
        if owns_task:
            async with guard:
                if inflight.get(user_id) is task:
                    del inflight[user_id]


async def _resolve_current_user(request: Request) -> tuple[str, Any | None]:
    user_id = _extract_jwt_payload(request)["user_id"]
    user_repo = getattr(request.app.state, "user_repo", None)
    if user_repo is None:
        return user_id, None
    user = await _get_user_row_for_auth(request, user_id, user_repo)
    if user is None:
        raise HTTPException(401, "User no longer exists — please re-login")
    return user_id, user


async def get_current_user(request: Request) -> Any:
    """Return the authenticated user row when a route needs user fields."""
    _, user = await _resolve_current_user(request)
    if user is None:
        raise HTTPException(500, "User repo not initialized")
    return user


async def get_current_user_id(request: Request) -> str:
    """Extract user_id from JWT and verify user exists. Returns 401 if user was deleted (e.g. DB reset)."""
    user_id, _ = await _resolve_current_user(request)
    return user_id


async def verify_thread_owner(
    thread_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[FastAPI, Depends(get_app)],
) -> str:
    """Verify that user_id owns the thread. Returns user_id."""
    runtime_state = inspect_owner_thread_runtime(app, thread_id)
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
