"""Contacts API router — /api/contacts endpoints."""

from __future__ import annotations

import time
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.chat.api.http.dependencies import get_contact_repo
from backend.web.core.dependencies import get_current_user_id
from storage.contracts import ContactEdgeRow

router = APIRouter(prefix="/api/contacts", tags=["contacts"])


class SetContactBody(BaseModel):
    target_user_id: str
    kind: Literal["normal", "hire", "visit", "blocked", "muted"]
    state: Literal["pending", "active", "rejected", "revoked"] = "active"


@router.get("")
async def list_contacts(
    user_id: Annotated[str, Depends(get_current_user_id)],
    contact_repo: Annotated[Any, Depends(get_contact_repo)],
):
    """List contacts (blocked/muted) for the current user."""
    try:
        if contact_repo is None:
            raise RuntimeError("chat bootstrap not attached: contact_repo")
        rows = contact_repo.list_for_user(user_id)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
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
    contact_repo: Annotated[Any, Depends(get_contact_repo)],
):
    """Upsert contact (block/mute/normal)."""
    try:
        if contact_repo is None:
            raise RuntimeError("chat bootstrap not attached: contact_repo")
        contact_repo.upsert(
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
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    return {"status": "ok", "kind": body.kind, "state": body.state}


@router.delete("/{target_id}")
async def delete_contact(
    target_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    contact_repo: Annotated[Any, Depends(get_contact_repo)],
):
    """Remove contact entry."""
    try:
        if contact_repo is None:
            raise RuntimeError("chat bootstrap not attached: contact_repo")
        contact_repo.delete(user_id, target_id)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    return {"status": "deleted"}
