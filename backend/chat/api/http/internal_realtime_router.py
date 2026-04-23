"""Internal realtime routes for cross-backend chat side effects."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.chat.api.http.dependencies import get_typing_tracker

router = APIRouter(prefix="/api/internal/realtime", tags=["chat-internal"])


class TypingStartBody(BaseModel):
    thread_id: str
    chat_id: str
    user_id: str


class TypingStopBody(BaseModel):
    thread_id: str


@router.post("/typing/start")
def start_typing(
    body: TypingStartBody,
    typing_tracker: Annotated[Any, Depends(get_typing_tracker)],
) -> dict[str, str]:
    typing_tracker.start_chat(body.thread_id, body.chat_id, body.user_id)
    return {"status": "ok"}


@router.post("/typing/stop")
def stop_typing(
    body: TypingStopBody,
    typing_tracker: Annotated[Any, Depends(get_typing_tracker)],
) -> dict[str, str]:
    typing_tracker.stop(body.thread_id)
    return {"status": "ok"}
