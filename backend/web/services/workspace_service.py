"""Workspace management service.

A workspace is a named directory on the host machine that can be shared across
multiple threads. Each thread can have at most one workspace_id; multiple threads
can reference the same workspace.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.web.utils.helpers import _get_container
from storage.contracts import WorkspaceRepo


def _now_utc() -> str:
    return datetime.now(UTC).isoformat()


def _repo() -> WorkspaceRepo:
    return _get_container().workspace_repo()


def create_workspace(host_path: str, name: str | None = None) -> dict[str, Any]:
    host = Path(host_path).expanduser().resolve()
    if not host.exists():
        raise ValueError(f"Workspace host_path does not exist: {host}")
    workspace_id = str(uuid.uuid4())
    now = _now_utc()
    repo = _repo()
    try:
        repo.create(workspace_id, str(host), name, now)
    finally:
        repo.close()
    return {"workspace_id": workspace_id, "host_path": str(host), "name": name, "created_at": now}


def get_workspace(workspace_id: str) -> dict[str, Any] | None:
    repo = _repo()
    try:
        return repo.get(workspace_id)
    finally:
        repo.close()


def list_workspaces() -> list[dict[str, Any]]:
    repo = _repo()
    try:
        return repo.list_all()
    finally:
        repo.close()


def delete_workspace(workspace_id: str) -> bool:
    repo = _repo()
    try:
        return repo.delete(workspace_id)
    finally:
        repo.close()
