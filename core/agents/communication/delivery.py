"""Delivery Strategy — narrow bottleneck for member-type-aware message delivery.

All message delivery (HTTP and logbook paths) converges through DeliveryRouter,
which dispatches to the right strategy based on member type. Adding a new member
type = one new class + one registration line.

Same pattern as SandboxProvider (ABC) → Docker/Daytona/E2B in the sandbox layer.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Protocol

from storage.contracts import MemberRow, MemberType

if TYPE_CHECKING:
    from storage.contracts import ConversationMemberRepo, MemberRepo

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# @@@delivery-bottleneck - Protocol + implementations + router
# ---------------------------------------------------------------------------


class DeliveryStrategy(Protocol):
    """How to deliver a message to a specific member type."""

    async def deliver(
        self,
        member: MemberRow,
        content: str,
        sender_name: str,
        conversation_id: str,
    ) -> dict: ...


class HumanDelivery:
    """Human members receive messages via conversation SSE — no extra action needed."""

    async def deliver(
        self, member: MemberRow, content: str, sender_name: str, conversation_id: str,
    ) -> dict:
        return {"routing": "sse_only", "member_id": member.id}


class MycelAgentDelivery:
    """Route message to our agent's brain thread via LangGraph."""

    def __init__(self, app: Any) -> None:
        self._app = app

    async def deliver(
        self, member: MemberRow, content: str, sender_name: str, conversation_id: str,
    ) -> dict:
        from backend.web.services.agent_pool import route_message_to_brain
        from core.runtime.middleware.queue import format_conversation_message

        brain_thread_id = f"brain-{member.id}"
        formatted = format_conversation_message(content, sender_name, conversation_id)
        result = await route_message_to_brain(self._app, brain_thread_id, formatted)
        return {**result, "member_id": member.id, "brain_thread_id": brain_thread_id}


class OpenClawDelivery:
    """Placeholder for external agent frameworks. Future: webhook/API call."""

    async def deliver(
        self, member: MemberRow, content: str, sender_name: str, conversation_id: str,
    ) -> dict:
        logger.info("OpenClaw delivery placeholder for member %s", member.id)
        return {"routing": "openclaw_placeholder", "member_id": member.id}


class DeliveryRouter:
    """Narrow bottleneck: resolves member type → delivery strategy.

    Both HTTP (conversations router) and logbook (_create_message_router)
    converge through this single point.
    """

    def __init__(self, strategies: dict[MemberType, DeliveryStrategy]) -> None:
        self._strategies = strategies

    async def deliver_to_conversation(
        self,
        conversation_id: str,
        sender_id: str,
        content: str,
        conv_member_repo: ConversationMemberRepo,
        member_repo: MemberRepo,
    ) -> list[dict]:
        """Deliver message to all non-sender members via their type-specific strategy."""
        members = conv_member_repo.list_members(conversation_id)
        sender = member_repo.get_by_id(sender_id)
        sender_name = sender.name if sender else "unknown"

        results = []
        for cm in members:
            if cm.member_id == sender_id:
                continue
            member = member_repo.get_by_id(cm.member_id)
            if not member:
                continue
            strategy = self._strategies.get(member.type)
            if not strategy:
                logger.warning("No delivery strategy for member type %s (member %s)", member.type, member.id)
                continue
            try:
                result = await strategy.deliver(member, content, sender_name, conversation_id)
                results.append(result)
                logger.info("Delivered to %s (%s): %s", member.name, member.type.value, result.get("routing"))
            except Exception:
                logger.exception("Delivery failed for member %s (%s)", member.id, member.type.value)
        return results
