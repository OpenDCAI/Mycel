"""Sandbox management endpoints."""

import asyncio
import subprocess
import sys
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.web.core.dependencies import get_current_user_id
from backend.web.services import sandbox_service

router = APIRouter(prefix="/api/sandbox", tags=["sandbox"])


def _runtime_http_error(exc: RuntimeError) -> HTTPException:
    message = str(exc)
    status = 404 if "not found" in message.lower() else 409
    return HTTPException(status, message)


async def _mutate_session_action(session_id: str, action: str, provider: str | None) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(
            sandbox_service.mutate_sandbox_session,
            session_id=session_id,
            action=action,
            provider_hint=provider,
        )
    except RuntimeError as e:
        raise _runtime_http_error(e) from e


@router.get("/types")
async def list_sandbox_types() -> dict[str, Any]:
    """List available sandbox types."""
    types = await asyncio.to_thread(sandbox_service.available_sandbox_types)
    return {"types": types}


@router.get("/pick-folder")
async def pick_folder() -> dict[str, Any]:
    """Open system folder picker dialog and return selected path."""
    try:
        if sys.platform == "darwin":  # macOS
            result = subprocess.run(
                [
                    "osascript",
                    "-e",
                    'POSIX path of (choose folder with prompt "选择工作目录")',
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0:
                path = result.stdout.strip()
                return {"path": path}
            else:
                raise HTTPException(400, "User cancelled folder selection")
        elif sys.platform == "win32":  # Windows
            # Use PowerShell folder browser
            ps_script = """
            Add-Type -AssemblyName System.Windows.Forms
            $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
            $dialog.Description = "选择工作目录"
            $dialog.ShowNewFolderButton = $true
            if ($dialog.ShowDialog() -eq 'OK') {
                Write-Output $dialog.SelectedPath
            }
            """
            result = subprocess.run(
                ["powershell", "-Command", ps_script],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0 and result.stdout.strip():
                path = result.stdout.strip()
                return {"path": path}
            else:
                raise HTTPException(400, "User cancelled folder selection")
        else:  # Linux
            # Try zenity first, fallback to kdialog
            try:
                result = subprocess.run(
                    ["zenity", "--file-selection", "--directory", "--title=选择工作目录"],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                if result.returncode == 0:
                    path = result.stdout.strip()
                    return {"path": path}
            except FileNotFoundError:
                # Try kdialog
                result = subprocess.run(
                    ["kdialog", "--getexistingdirectory", ".", "--title", "选择工作目录"],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                if result.returncode == 0:
                    path = result.stdout.strip()
                    return {"path": path}
            raise HTTPException(400, "User cancelled folder selection")
    except subprocess.TimeoutExpired:
        raise HTTPException(408, "Folder selection timed out")
    # @@@http_passthrough - keep explicit business/status errors from selection branches intact
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to open folder picker: {str(e)}") from e


@router.get("/sessions")
async def list_sandbox_sessions() -> dict[str, Any]:
    """List all sandbox sessions across providers."""
    _, managers = await asyncio.to_thread(sandbox_service.init_providers_and_managers)
    sessions = await asyncio.to_thread(sandbox_service.load_all_sessions, managers)
    return {"sessions": sessions}


@router.get("/leases/mine")
async def list_my_leases(
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> dict[str, Any]:
    leases = await asyncio.to_thread(sandbox_service.list_user_leases, user_id)
    return {"leases": leases}


@router.get("/sessions/{session_id}/metrics")
async def get_session_metrics(session_id: str, provider: str | None = Query(default=None)) -> dict[str, Any]:
    """Get metrics for a specific sandbox session."""
    try:
        return await asyncio.to_thread(sandbox_service.get_session_metrics, session_id, provider)
    except RuntimeError as e:
        raise _runtime_http_error(e) from e


@router.post("/sessions/{session_id}/pause")
async def pause_sandbox_session(session_id: str, provider: str | None = Query(default=None)) -> dict[str, Any]:
    """Pause a sandbox session."""
    return await _mutate_session_action(session_id, "pause", provider)


@router.post("/sessions/{session_id}/resume")
async def resume_sandbox_session(session_id: str, provider: str | None = Query(default=None)) -> dict[str, Any]:
    """Resume a paused sandbox session."""
    return await _mutate_session_action(session_id, "resume", provider)


@router.delete("/sessions/{session_id}")
async def destroy_sandbox_session(session_id: str, provider: str | None = Query(default=None)) -> dict[str, Any]:
    """Destroy a sandbox session."""
    return await _mutate_session_action(session_id, "destroy", provider)
