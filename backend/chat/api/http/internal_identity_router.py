from __future__ import annotations

import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.chat.api.http.dependencies import get_user_repo
from storage.contracts import UserRow, UserType

router = APIRouter(prefix="/api/internal/identity", tags=["chat-internal"])


class CreateExternalUserBody(BaseModel):
    user_id: str
    display_name: str


def _serialize_user(user: UserRow) -> dict[str, Any]:
    return {
        "id": user.id,
        "type": user.type.value,
        "display_name": user.display_name,
        "owner_user_id": user.owner_user_id,
        "agent_config_id": user.agent_config_id,
    }


@router.post("/users/external")
def create_external_user(
    body: CreateExternalUserBody,
    user_repo: Annotated[Any, Depends(get_user_repo)],
) -> dict[str, Any]:
    existing = user_repo.get_by_id(body.user_id)
    if existing is not None:
        raise HTTPException(409, "User already exists")

    row = UserRow(
        id=body.user_id,
        type=UserType.EXTERNAL,
        display_name=body.display_name,
        created_at=time.time(),
    )
    user_repo.create(row)
    return _serialize_user(row)


@router.get("/users")
def list_users(
    type: str,
    user_repo: Annotated[Any, Depends(get_user_repo)],
) -> list[dict[str, Any]]:
    return [_serialize_user(row) for row in user_repo.list_by_type(type)]
