"""Workspace CRUD endpoints."""

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.web.services.workspace_service import (
    create_workspace,
    delete_workspace,
    get_workspace,
    list_workspaces,
)

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])


class CreateWorkspaceRequest(BaseModel):
    host_path: str
    name: str | None = None


@router.post("")
async def create_workspace_endpoint(payload: CreateWorkspaceRequest) -> dict[str, Any]:
    """Create a workspace pointing to a host directory."""
    try:
        return await asyncio.to_thread(create_workspace, payload.host_path, payload.name)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.get("")
async def list_workspaces_endpoint() -> dict[str, Any]:
    """List all workspaces."""
    workspaces = await asyncio.to_thread(list_workspaces)
    return {"workspaces": workspaces}


@router.get("/{workspace_id}")
async def get_workspace_endpoint(workspace_id: str) -> dict[str, Any]:
    """Get a workspace by ID."""
    ws = await asyncio.to_thread(get_workspace, workspace_id)
    if ws is None:
        raise HTTPException(404, f"Workspace not found: {workspace_id}")
    return ws


@router.delete("/{workspace_id}")
async def delete_workspace_endpoint(workspace_id: str) -> dict[str, Any]:
    """Delete a workspace record (does not remove host directory)."""
    deleted = await asyncio.to_thread(delete_workspace, workspace_id)
    if not deleted:
        raise HTTPException(404, f"Workspace not found: {workspace_id}")
    return {"ok": True, "workspace_id": workspace_id}
