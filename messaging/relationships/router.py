"""Relationship API router — /api/relationships endpoints."""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from backend.web.core.dependencies import get_app, get_current_user_id
from messaging.contracts import RelationshipRow
from messaging.relationships.state_machine import TransitionError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/relationships", tags=["relationships"])


class RelationshipRequestBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_user_id: str
    actor_user_id: str | None = None


class RelationshipActionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor_user_id: str | None = None


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


def _resolve_actor_user_id(app: Any, current_user_id: str, actor_user_id: str | None) -> str:
    if actor_user_id is None or actor_user_id == current_user_id:
        return current_user_id
    user_repo = getattr(app.state, "user_repo", None)
    if user_repo is None:
        raise HTTPException(503, "User repo unavailable")
    actor = user_repo.get_by_id(actor_user_id)
    if actor is None:
        raise HTTPException(404, "Actor user not found")
    if getattr(actor, "owner_user_id", None) != current_user_id:
        raise HTTPException(403, "Actor user does not belong to you")
    return actor_user_id


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
    actor_user_id = _resolve_actor_user_id(app, user_id, body.actor_user_id)
    if actor_user_id == body.target_user_id:
        raise HTTPException(400, "Cannot request relationship with yourself")
    try:
        row = svc.request(actor_user_id, body.target_user_id)
        return _row_to_dict(row, actor_user_id)
    except TransitionError as e:
        raise HTTPException(409, str(e))


@router.post("/{relationship_id}/approve")
async def approve_relationship(
    relationship_id: str,
    body: RelationshipActionBody,
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)],
):
    svc = _get_rel_service(app)
    actor_user_id = _resolve_actor_user_id(app, user_id, body.actor_user_id)
    existing = _get_existing(svc, relationship_id, actor_user_id)
    requester_id, _ = _resolve_parties(existing, actor_user_id)
    if actor_user_id == requester_id:
        raise HTTPException(409, "Cannot approve your own request")
    try:
        return _row_to_dict(svc.approve(actor_user_id, requester_id), actor_user_id)
    except TransitionError as e:
        raise HTTPException(409, str(e))


@router.post("/{relationship_id}/reject")
async def reject_relationship(
    relationship_id: str,
    body: RelationshipActionBody,
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)],
):
    svc = _get_rel_service(app)
    actor_user_id = _resolve_actor_user_id(app, user_id, body.actor_user_id)
    existing = _get_existing(svc, relationship_id, actor_user_id)
    requester_id, _ = _resolve_parties(existing, actor_user_id)
    if actor_user_id == requester_id:
        raise HTTPException(409, "Cannot reject your own request")
    try:
        return _row_to_dict(svc.reject(actor_user_id, requester_id), actor_user_id)
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
    actor_user_id = _resolve_actor_user_id(app, user_id, body.actor_user_id)
    existing = _get_existing(svc, relationship_id, actor_user_id)
    _, other_id = _resolve_parties(existing, actor_user_id)
    try:
        return _row_to_dict(svc.upgrade(actor_user_id, other_id), actor_user_id)
    except TransitionError as e:
        raise HTTPException(409, str(e))


@router.post("/{relationship_id}/revoke")
async def revoke_relationship(
    relationship_id: str,
    body: RelationshipActionBody,
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)],
):
    svc = _get_rel_service(app)
    actor_user_id = _resolve_actor_user_id(app, user_id, body.actor_user_id)
    existing = _get_existing(svc, relationship_id, actor_user_id)
    _, other_id = _resolve_parties(existing, actor_user_id)
    try:
        return _row_to_dict(svc.revoke(actor_user_id, other_id), actor_user_id)
    except TransitionError as e:
        raise HTTPException(409, str(e))


@router.post("/{relationship_id}/downgrade")
async def downgrade_relationship(
    relationship_id: str,
    body: RelationshipActionBody,
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)],
):
    svc = _get_rel_service(app)
    actor_user_id = _resolve_actor_user_id(app, user_id, body.actor_user_id)
    existing = _get_existing(svc, relationship_id, actor_user_id)
    _, other_id = _resolve_parties(existing, actor_user_id)
    try:
        return _row_to_dict(svc.downgrade(actor_user_id, other_id), actor_user_id)
    except TransitionError as e:
        raise HTTPException(409, str(e))
