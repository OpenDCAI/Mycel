"""Contacts API router — /api/contacts endpoints."""

from __future__ import annotations

import logging
import time
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.web.core.dependencies import get_app, get_current_user_id
from storage.contracts import ContactRow

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/contacts", tags=["contacts"])


class SetContactBody(BaseModel):
    target_id: str
    relation: Literal["normal", "blocked", "muted"]


@router.get("")
async def list_contacts(
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)],
):
    """List contacts (blocked/muted) for the current user."""
    rows = app.state.contact_repo.list_for_user(user_id)
    return [
        {
            "owner_user_id": row.owner_id,
            "target_user_id": row.target_id,
            "relation": row.relation,
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
        ContactRow(
            owner_id=user_id,
            target_id=body.target_id,
            relation=body.relation,
            created_at=time.time(),
            updated_at=time.time(),
        )
    )
    return {"status": "ok", "relation": body.relation}


@router.delete("/{target_id}")
async def delete_contact(
    target_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)],
):
    """Remove contact entry."""
    app.state.contact_repo.delete(user_id, target_id)
    return {"status": "deleted"}
