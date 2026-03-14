"""FastAPI dependency injection functions."""

import asyncio
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.web.services.agent_pool import get_or_create_agent, resolve_thread_sandbox
from sandbox.thread_context import set_current_thread_id

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_app(request: Request) -> FastAPI:
    """Get FastAPI app instance from request."""
    return request.app


async def get_current_member_id(
    app: Annotated[FastAPI, Depends(get_app)],
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> str:
    """Extract and verify JWT, return member_id. 401 on failure.

    Also verifies the member still exists in DB — rejects ghost tokens
    from stale sessions after DB cleanup.
    """
    if credentials is None:
        raise HTTPException(401, "Missing authorization header")
    auth_service = getattr(app.state, "auth_service", None)
    if auth_service is None:
        raise HTTPException(500, "Auth service not initialized")
    try:
        member_id = auth_service.verify_token(credentials.credentials)
    except ValueError as e:
        raise HTTPException(401, str(e))
    # @@@ghost-token - verify member still exists (DB may have been wiped)
    member_repo = getattr(app.state, "member_repo", None)
    if member_repo and member_repo.get_by_id(member_id) is None:
        raise HTTPException(401, "Member no longer exists")
    return member_id


# @@@thread-auth - verify requesting user owns the brain thread
async def verify_thread_owner(
    thread_id: str,
    member_id: Annotated[str, Depends(get_current_member_id)],
    app: Annotated[FastAPI, Depends(get_app)],
) -> str:
    """Verify requesting user owns the brain thread. Returns member_id.

    - brain-{agent_id} threads: checks agent's owner_id == member_id → 403 if not
    - Non-brain threads: just require valid JWT (legacy compat)
    """
    if not thread_id.startswith("brain-"):
        return member_id

    agent_member_id = thread_id.removeprefix("brain-")
    member_repo = getattr(app.state, "member_repo", None)
    if not member_repo:
        raise HTTPException(500, "Member repo not initialized")

    agent = member_repo.get_by_id(agent_member_id)
    if not agent:
        raise HTTPException(404, "Agent not found")

    if agent.owner_id != member_id:
        raise HTTPException(403, "Not authorized to access this thread")

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
