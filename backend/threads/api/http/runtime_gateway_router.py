"""Internal runtime-ingress routes for cross-backend Agent Runtime protocol traffic."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from backend.threads.runtime_access import get_agent_runtime_gateway
from backend.web.core.dependencies import get_app
from protocols.agent_runtime import (
    chat_delivery_envelope_from_payload,
    chat_delivery_result_to_payload,
    thread_input_envelope_from_payload,
    thread_input_result_to_payload,
)

router = APIRouter(prefix="/api/internal/agent-runtime", tags=["threads-internal"])


@router.post("/chat-deliveries")
async def dispatch_chat_delivery(
    payload: dict[str, Any],
    app: Annotated[Any, Depends(get_app)],
) -> dict[str, Any]:
    result = await get_agent_runtime_gateway(app).dispatch_chat(chat_delivery_envelope_from_payload(payload))
    return chat_delivery_result_to_payload(result)


@router.post("/thread-input")
async def dispatch_thread_input(
    payload: dict[str, Any],
    app: Annotated[Any, Depends(get_app)],
) -> dict[str, Any]:
    result = await get_agent_runtime_gateway(app).dispatch_thread_input(thread_input_envelope_from_payload(payload))
    return thread_input_result_to_payload(result)
