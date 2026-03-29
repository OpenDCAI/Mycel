"""Thread file browsing endpoints."""

import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from backend.web.core.dependencies import get_app, verify_thread_owner
from backend.web.services.agent_pool import resolve_thread_sandbox
from backend.web.services.member_volume_service import (
    get_lease_volume_source,
    save_file,
    list_volume_files,
    resolve_volume_file,
    delete_volume_file,
)
from backend.web.utils.helpers import resolve_local_workspace_path
from sandbox.thread_context import set_current_thread_id

router = APIRouter(
    prefix="/api/threads/{thread_id}/files",
    tags=["thread-files"],
    dependencies=[Depends(verify_thread_owner)],
)
# @@@public-download — download is accessed via <a href> which can't carry auth headers
_public = APIRouter(prefix="/api/threads/{thread_id}/files", tags=["thread-files"])


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
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, str(e)) from e
    return {"thread_id": thread_id, **payload}


@router.get("/channels")
async def get_sandbox_files(
    thread_id: str,

) -> dict[str, Any]:
    """Get thread-scoped upload/download channel paths."""
    source = await asyncio.to_thread(get_lease_volume_source, thread_id)
    return {"thread_id": thread_id, "files_path": str(source.host_path)}


_MAX_UPLOAD_BYTES = 100 * 1024 * 1024  # 100 MB


@router.post("/upload")
async def upload_file(
    thread_id: str,
    file: UploadFile = File(...),
    path: str | None = Query(default=None),

    app: Annotated[Any, Depends(get_app)] = None,
) -> dict[str, Any]:
    """Upload a file into thread sandbox files."""
    if not file.filename and not path:
        raise HTTPException(400, "Missing upload path: provide query path or filename")
    relative_path = path or file.filename or ""
    content = await file.read(_MAX_UPLOAD_BYTES + 1)
    if len(content) > _MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"Upload exceeds {_MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit")
    try:
        payload = await asyncio.to_thread(
            save_file,
            thread_id=thread_id,
            relative_path=relative_path,
            content=content,
        )

    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return payload


@_public.get("/download")
async def download_file(
    thread_id: str,
    path: str = Query(...),
) -> FileResponse:
    """Download a file from thread-scoped files directory."""
    try:
        target = await asyncio.to_thread(
            resolve_volume_file,
            thread_id=thread_id,
            relative_path=path,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    return FileResponse(path=str(target), filename=target.name, media_type="application/octet-stream")


@router.delete("/files")
async def delete_workspace_file(
    thread_id: str,
    path: str = Query(...),

) -> dict[str, Any]:
    """Delete a file from workspace."""
    try:
        await asyncio.to_thread(
            delete_volume_file,
            thread_id=thread_id,
            relative_path=path,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    return {"ok": True, "path": path}


@router.get("/channel-files")
async def list_channel_files(
    thread_id: str,

) -> dict[str, Any]:
    """List files under thread-scoped files directory."""
    try:
        entries = await asyncio.to_thread(
            list_volume_files,
            thread_id=thread_id,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"thread_id": thread_id, "entries": entries}
