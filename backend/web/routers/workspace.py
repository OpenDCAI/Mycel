"""Workspace file browsing endpoints."""

import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.web.core.dependencies import get_app
from backend.web.services.agent_pool import resolve_thread_sandbox
from backend.web.utils.helpers import resolve_local_workspace_path
from sandbox.thread_context import set_current_thread_id

router = APIRouter(prefix="/api/threads/{thread_id}/workspace", tags=["workspace"])


@router.get("/list")
async def list_workspace_path(
    thread_id: str,
    path: str | None = Query(default=None),
    app: Annotated[Any, Depends(get_app)] = None,
) -> dict[str, Any]:
    """List files and directories in workspace path."""
    sandbox_type = resolve_thread_sandbox(app, thread_id)
    if sandbox_type == "local":
        from core.tools.filesystem.local_backend import LocalBackend

        backend = LocalBackend()
        target = resolve_local_workspace_path(
            path,
            thread_id=thread_id,
            thread_cwd_map=app.state.thread_cwd,
        )
        result = backend.list_dir(str(target))
        if result.error:
            raise HTTPException(400, result.error)
        return {
            "thread_id": thread_id,
            "path": str(target),
            "entries": [
                {"name": e.name, "is_dir": e.is_dir, "size": e.size, "children_count": e.children_count}
                for e in result.entries
            ],
        }

    # Remote sandbox
    from backend.web.services.agent_pool import get_or_create_agent

    try:
        set_current_thread_id(thread_id)
        agent = await get_or_create_agent(app, sandbox_type, thread_id=thread_id)
    # @@@http_passthrough - preserve policy/validation errors from agent creation
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(503, f"Sandbox agent init failed for {sandbox_type}: {e}") from e

    if not hasattr(agent, "_sandbox"):
        raise HTTPException(400, "Agent has no sandbox")
    if agent._sandbox.name == "local":
        raise HTTPException(400, "Agent has no remote sandbox")

    def _list_remote() -> dict[str, Any]:
        set_current_thread_id(thread_id)
        capability = agent._sandbox.manager.get_sandbox(thread_id)
        target = path or capability._session.terminal.get_state().cwd
        result = capability.fs.list_dir(target)
        if result.error:
            raise RuntimeError(result.error)
        return {
            "path": target,
            "entries": [
                {"name": e.name, "is_dir": e.is_dir, "size": e.size, "children_count": e.children_count}
                for e in result.entries
            ],
        }

    try:
        payload = await asyncio.to_thread(_list_remote)
    # @@@http_passthrough - preserve explicit status from remote capability path
    except HTTPException:
        raise
    except RuntimeError as e:
        raise HTTPException(400, str(e)) from e
    return {"thread_id": thread_id, **payload}


@router.get("/read")
async def read_workspace_file(
    thread_id: str,
    path: str = Query(...),
    app: Annotated[Any, Depends(get_app)] = None,
) -> dict[str, Any]:
    """Read file content from workspace."""
    sandbox_type = resolve_thread_sandbox(app, thread_id)
    if sandbox_type == "local":
        from core.tools.filesystem.local_backend import LocalBackend

        backend = LocalBackend()
        target = resolve_local_workspace_path(
            path,
            thread_id=thread_id,
            thread_cwd_map=app.state.thread_cwd,
        )
        try:
            data = backend.read_file(str(target))
        except Exception as e:
            raise HTTPException(400, str(e)) from e
        return {"thread_id": thread_id, "path": str(target), "content": data.content, "size": data.size}

    # Remote sandbox
    from backend.web.services.agent_pool import get_or_create_agent

    try:
        set_current_thread_id(thread_id)
        agent = await get_or_create_agent(app, sandbox_type, thread_id=thread_id)
    # @@@http_passthrough - preserve policy/validation errors from agent creation
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(503, f"Sandbox agent init failed for {sandbox_type}: {e}") from e

    if not hasattr(agent, "_sandbox"):
        raise HTTPException(400, "Agent has no sandbox")
    if agent._sandbox.name == "local":
        raise HTTPException(400, "Agent has no remote sandbox")

    def _read_remote() -> dict[str, Any]:
        set_current_thread_id(thread_id)
        capability = agent._sandbox.manager.get_sandbox(thread_id)
        data = capability.fs.read_file(path)
        return {"path": path, "content": data.content, "size": data.size}

    try:
        payload = await asyncio.to_thread(_read_remote)
    # @@@http_passthrough - preserve explicit status from remote capability path
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, str(e)) from e
    return {"thread_id": thread_id, **payload}
