from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from backend.chat.api.http.dependencies import (
    get_current_user_id,
    get_relationship_service,
)
from messaging.contracts import RelationshipRow
from messaging.relationships.state_machine import TransitionError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/relationships", tags=["relationships"])


class RelationshipRequestBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_user_id: str
    message: str | None = None


class RelationshipActionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pass


def _get_existing(svc, relationship_id: str, user_id: str) -> dict:
    existing = svc.get_by_id(relationship_id)
    if not existing:
        raise HTTPException(404, "Relationship not found")
    if user_id not in (existing["user_low"], existing["user_high"]):
        raise HTTPException(403, "Not a party of this relationship")
    return existing


def _resolve_parties(existing: dict, viewer_user_id: str) -> tuple[str, str]:
    requester_id = existing["initiator_user_id"]
    other_id = existing["user_high"] if viewer_user_id == existing["user_low"] else existing["user_low"]
    return requester_id, other_id


def _row_to_dict(row: RelationshipRow, viewer_id: str) -> dict:
    other_id = row.user_high if viewer_id == row.user_low else row.user_low
    is_requester = row.state == "pending" and viewer_id == row.initiator_user_id
    return {
        "id": row.id,
        "other_user_id": other_id,
        "state": row.state,
        "is_requester": is_requester,
        "message": row.message,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


@router.get("")
def list_relationships(
    user_id: Annotated[str, Depends(get_current_user_id)],
    relationship_service: Annotated[Any, Depends(get_relationship_service)],
):
    rows = relationship_service.list_for_user(user_id)
    return [_row_to_dict(r, user_id) for r in rows]


@router.post("/request")
def request_relationship(
    body: RelationshipRequestBody,
    user_id: Annotated[str, Depends(get_current_user_id)],
    relationship_service: Annotated[Any, Depends(get_relationship_service)],
):
    if user_id == body.target_user_id:
        raise HTTPException(400, "Cannot request relationship with yourself")
    try:
        row = relationship_service.request(user_id, body.target_user_id, body.message)
        return _row_to_dict(row, user_id)
    except TransitionError as e:
        raise HTTPException(409, str(e))


@router.post("/{relationship_id}/approve")
def approve_relationship(
    relationship_id: str,
    body: RelationshipActionBody,
    user_id: Annotated[str, Depends(get_current_user_id)],
    relationship_service: Annotated[Any, Depends(get_relationship_service)],
):
    existing = _get_existing(relationship_service, relationship_id, user_id)
    requester_id, _ = _resolve_parties(existing, user_id)
    if user_id == requester_id:
        raise HTTPException(409, "Cannot approve your own request")
    try:
        return _row_to_dict(relationship_service.approve(user_id, requester_id), user_id)
    except TransitionError as e:
        raise HTTPException(409, str(e))


@router.post("/{relationship_id}/reject")
def reject_relationship(
    relationship_id: str,
    body: RelationshipActionBody,
    user_id: Annotated[str, Depends(get_current_user_id)],
    relationship_service: Annotated[Any, Depends(get_relationship_service)],
):
    existing = _get_existing(relationship_service, relationship_id, user_id)
    requester_id, _ = _resolve_parties(existing, user_id)
    if user_id == requester_id:
        raise HTTPException(409, "Cannot reject your own request")
    try:
        return _row_to_dict(relationship_service.reject(user_id, requester_id), user_id)
    except TransitionError as e:
        raise HTTPException(409, str(e))


@router.post("/{relationship_id}/upgrade")
def upgrade_relationship(
    relationship_id: str,
    body: RelationshipActionBody,
    user_id: Annotated[str, Depends(get_current_user_id)],
    relationship_service: Annotated[Any, Depends(get_relationship_service)],
):
    existing = _get_existing(relationship_service, relationship_id, user_id)
    _, other_id = _resolve_parties(existing, user_id)
    try:
        return _row_to_dict(relationship_service.upgrade(user_id, other_id), user_id)
    except TransitionError as e:
        raise HTTPException(409, str(e))


@router.post("/{relationship_id}/revoke")
def revoke_relationship(
    relationship_id: str,
    body: RelationshipActionBody,
    user_id: Annotated[str, Depends(get_current_user_id)],
    relationship_service: Annotated[Any, Depends(get_relationship_service)],
):
    existing = _get_existing(relationship_service, relationship_id, user_id)
    _, other_id = _resolve_parties(existing, user_id)
    try:
        return _row_to_dict(relationship_service.revoke(user_id, other_id), user_id)
    except TransitionError as e:
        raise HTTPException(409, str(e))


@router.post("/{relationship_id}/downgrade")
def downgrade_relationship(
    relationship_id: str,
    body: RelationshipActionBody,
    user_id: Annotated[str, Depends(get_current_user_id)],
    relationship_service: Annotated[Any, Depends(get_relationship_service)],
):
    existing = _get_existing(relationship_service, relationship_id, user_id)
    _, other_id = _resolve_parties(existing, user_id)
    try:
        return _row_to_dict(relationship_service.downgrade(user_id, other_id), user_id)
    except TransitionError as e:
        raise HTTPException(409, str(e))
