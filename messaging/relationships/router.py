"""Relationship API router — /api/relationships endpoints."""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.web.core.dependencies import get_app, get_current_user_id
from messaging.contracts import RelationshipRow
from messaging.relationships.state_machine import TransitionError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/relationships", tags=["relationships"])


class RelationshipRequestBody(BaseModel):
    target_user_id: str


class RelationshipActionBody(BaseModel):
    hire_snapshot: dict[str, Any] | None = None


def _get_rel_service(app: Any):
    svc = getattr(app.state, "relationship_service", None)
    if svc is None:
        raise HTTPException(503, "Relationship service unavailable")
    return svc


def _get_existing(svc, relationship_id: str, user_id: str) -> dict:
    existing = svc.get_by_id(relationship_id)
    if not existing:
        raise HTTPException(404, "Relationship not found")
    if user_id not in (existing["user_low"], existing["user_high"]):
        raise HTTPException(403, "Not a party of this relationship")
    return existing


def _resolve_parties(existing: dict, actor_id: str) -> tuple[str, str]:
    """Return (requester_id, other_id) from a relationship row and actor."""
    requester_id = existing["initiator_user_id"]
    other_id = existing["user_high"] if actor_id == existing["user_low"] else existing["user_low"]
    return requester_id, other_id


def _row_to_dict(row: RelationshipRow, viewer_id: str) -> dict:
    other_id = row.user_high if viewer_id == row.user_low else row.user_low
    is_requester = row.state == "pending" and viewer_id == row.initiator_user_id
    return {
        "id": row.id,
        "other_user_id": other_id,
        "state": row.state,
        "is_requester": is_requester,
        "hire_granted_at": row.hire_granted_at.isoformat() if row.hire_granted_at else None,
        "hire_revoked_at": row.hire_revoked_at.isoformat() if row.hire_revoked_at else None,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


@router.get("")
async def list_relationships(
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)],
):
    svc = _get_rel_service(app)
    rows = svc.list_for_user(user_id)
    return [_row_to_dict(r, user_id) for r in rows]


@router.post("/request")
async def request_relationship(
    body: RelationshipRequestBody,
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)],
):
    svc = _get_rel_service(app)
    if user_id == body.target_user_id:
        raise HTTPException(400, "Cannot request relationship with yourself")
    try:
        row = svc.request(user_id, body.target_user_id)
        return _row_to_dict(row, user_id)
    except TransitionError as e:
        raise HTTPException(409, str(e))


@router.post("/{relationship_id}/approve")
async def approve_relationship(
    relationship_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)],
):
    svc = _get_rel_service(app)
    existing = _get_existing(svc, relationship_id, user_id)
    requester_id, _ = _resolve_parties(existing, user_id)
    if user_id == requester_id:
        raise HTTPException(409, "Cannot approve your own request")
    try:
        return _row_to_dict(svc.approve(user_id, requester_id), user_id)
    except TransitionError as e:
        raise HTTPException(409, str(e))


@router.post("/{relationship_id}/reject")
async def reject_relationship(
    relationship_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)],
):
    svc = _get_rel_service(app)
    existing = _get_existing(svc, relationship_id, user_id)
    requester_id, _ = _resolve_parties(existing, user_id)
    if user_id == requester_id:
        raise HTTPException(409, "Cannot reject your own request")
    try:
        return _row_to_dict(svc.reject(user_id, requester_id), user_id)
    except TransitionError as e:
        raise HTTPException(409, str(e))


@router.post("/{relationship_id}/upgrade")
async def upgrade_relationship(
    relationship_id: str,
    body: RelationshipActionBody,
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)],
):
    svc = _get_rel_service(app)
    existing = _get_existing(svc, relationship_id, user_id)
    _, other_id = _resolve_parties(existing, user_id)
    try:
        return _row_to_dict(svc.upgrade(user_id, other_id, snapshot=body.hire_snapshot), user_id)
    except TransitionError as e:
        raise HTTPException(409, str(e))


@router.post("/{relationship_id}/revoke")
async def revoke_relationship(
    relationship_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)],
):
    svc = _get_rel_service(app)
    existing = _get_existing(svc, relationship_id, user_id)
    _, other_id = _resolve_parties(existing, user_id)
    try:
        return _row_to_dict(svc.revoke(user_id, other_id), user_id)
    except TransitionError as e:
        raise HTTPException(409, str(e))


@router.post("/{relationship_id}/downgrade")
async def downgrade_relationship(
    relationship_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)],
):
    svc = _get_rel_service(app)
    existing = _get_existing(svc, relationship_id, user_id)
    _, other_id = _resolve_parties(existing, user_id)
    try:
        return _row_to_dict(svc.downgrade(user_id, other_id), user_id)
    except TransitionError as e:
        raise HTTPException(409, str(e))
