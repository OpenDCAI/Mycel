"""Contacts API router — /api/contacts endpoints."""

from __future__ import annotations

import time
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.web.core.dependencies import get_app, get_current_user_id
from storage.contracts import ContactEdgeRow

router = APIRouter(prefix="/api/contacts", tags=["contacts"])


class SetContactBody(BaseModel):
    target_user_id: str
    kind: Literal["normal", "hire", "visit", "blocked", "muted"]
    state: Literal["pending", "active", "rejected", "revoked"] = "active"


@router.get("")
async def list_contacts(
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)],
):
    """List contacts (blocked/muted) for the current user."""
    rows = app.state.contact_repo.list_for_user(user_id)
    return [
        {
            "source_user_id": row.source_user_id,
            "target_user_id": row.target_user_id,
            "kind": row.kind,
            "state": row.state,
            "muted": row.muted,
            "blocked": row.blocked,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
        for row in rows
    ]


@router.post("")
async def set_contact(
    body: SetContactBody,
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)],
):
    """Upsert contact (block/mute/normal)."""
    app.state.contact_repo.upsert(
        ContactEdgeRow(
            source_user_id=user_id,
            target_user_id=body.target_user_id,
            kind=body.kind,
            state=body.state,
            muted=body.kind == "muted",
            blocked=body.kind == "blocked",
            created_at=time.time(),
            updated_at=time.time(),
        )
    )
    return {"status": "ok", "kind": body.kind, "state": body.state}


@router.delete("/{target_id}")
async def delete_contact(
    target_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)],
):
    """Remove contact entry."""
    app.state.contact_repo.delete(user_id, target_id)
    return {"status": "deleted"}
