"""Workspace file browsing endpoints — browse, read, download from sandbox filesystem."""

import asyncio
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

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
    except Exception as e:
        raise HTTPException(400, str(e)) from e
    return {"thread_id": thread_id, **payload}


@router.get("/download")
async def download_workspace_file(
    thread_id: str,
    path: str = Query(...),
    app: Annotated[Any, Depends(get_app)] = None,
) -> FileResponse:
    """Download a file directly from sandbox filesystem."""
    sandbox_type = resolve_thread_sandbox(app, thread_id)
    if sandbox_type == "local":
        target = resolve_local_workspace_path(
            path,
            thread_id=thread_id,
            thread_cwd_map=app.state.thread_cwd,
        )
        if not target.is_file():
            raise HTTPException(404, f"File not found: {path}")
        return FileResponse(path=str(target), filename=target.name, media_type="application/octet-stream")

    raise HTTPException(501, "Remote sandbox download not yet supported")


_MAX_UPLOAD_BYTES = 100 * 1024 * 1024  # 100 MB


@router.post("/upload")
async def upload_workspace_file(
    thread_id: str,
    file: UploadFile = File(...),
    path: str | None = Query(default=None),
    app: Annotated[Any, Depends(get_app)] = None,
) -> dict[str, Any]:
    """Upload a file directly to sandbox filesystem."""
    sandbox_type = resolve_thread_sandbox(app, thread_id)
    if sandbox_type != "local":
        raise HTTPException(501, "Remote sandbox upload not yet supported")

    relative_path = path or file.filename or "uploaded_file"
    content = await file.read(_MAX_UPLOAD_BYTES + 1)
    if len(content) > _MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"Upload exceeds {_MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit")

    target = resolve_local_workspace_path(
        relative_path,
        thread_id=thread_id,
        thread_cwd_map=app.state.thread_cwd,
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)

    return {
        "thread_id": thread_id,
        "path": str(target),
        "filename": target.name,
        "size_bytes": len(content),
    }
