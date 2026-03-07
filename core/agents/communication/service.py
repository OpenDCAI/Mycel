"""SendMessage Service - P2 inter-agent communication.

Registers a SendMessage tool that routes messages between agents
via MessageQueueManager, using AgentRegistry for name resolution.
"""

from __future__ import annotations

import json
import logging
from html import escape

from core.agents.registry import AgentRegistry
from core.queue.manager import MessageQueueManager
from core.runtime.registry import ToolEntry, ToolMode, ToolRegistry

logger = logging.getLogger(__name__)

SEND_MESSAGE_SCHEMA = {
    "name": "SendMessage",
    "description": (
        "Send a message to another agent. "
        "type='message' for DMs, 'broadcast' for all agents, "
        "'shutdown_request' to request shutdown, 'shutdown_response' to respond, "
        "'plan_approval_response' to approve/reject a plan."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "type": {
                "type": "string",
                "enum": [
                    "message",
                    "broadcast",
                    "shutdown_request",
                    "shutdown_response",
                    "plan_approval_response",
                ],
                "description": "Message type",
            },
            "recipient": {
                "type": "string",
                "description": "Target agent name (required for message/shutdown_request)",
            },
            "content": {
                "type": "string",
                "description": "Message content",
            },
            "summary": {
                "type": "string",
                "description": "5-10 word summary shown as preview",
            },
            "approve": {
                "type": "boolean",
                "description": "For shutdown_response: whether to approve",
            },
            "request_id": {
                "type": "string",
                "description": "For shutdown_response: request ID to respond to",
            },
        },
        "required": ["type", "content"],
    },
}


def _format_agent_message(
    msg_type: str,
    content: str,
    sender_thread: str,
    summary: str | None = None,
    approve: bool | None = None,
    request_id: str | None = None,
) -> str:
    """Format an inter-agent message as system-reminder XML."""
    payload = {
        "message_type": msg_type,
        "content": content,
        "sender_thread": sender_thread,
    }
    if summary is not None:
        payload["summary"] = summary
    if approve is not None:
        payload["approve"] = approve
    if request_id is not None:
        payload["request_id"] = request_id

    escaped = escape(json.dumps(payload, ensure_ascii=False))
    return (
        "<system-reminder>\n"
        "<agent-message>\n"
        f"  {escaped}\n"
        "</agent-message>\n"
        "</system-reminder>"
    )


class SendMessageService:
    """Registers SendMessage tool into ToolRegistry for inter-agent communication."""

    def __init__(
        self,
        registry: ToolRegistry,
        agent_registry: AgentRegistry,
        queue_manager: MessageQueueManager,
        current_thread_id: str,
    ):
        self._agent_registry = agent_registry
        self._queue_manager = queue_manager
        self._current_thread_id = current_thread_id

        registry.register(ToolEntry(
            name="SendMessage",
            mode=ToolMode.INLINE,
            schema=SEND_MESSAGE_SCHEMA,
            handler=self._send,
            source="SendMessageService",
        ))

    async def _send(
        self,
        type: str,
        content: str,
        recipient: str | None = None,
        summary: str | None = None,
        approve: bool | None = None,
        request_id: str | None = None,
    ) -> str:
        if type == "message":
            return await self._send_direct(content, recipient, summary)
        elif type == "broadcast":
            return await self._send_broadcast(content, summary)
        elif type == "shutdown_request":
            return await self._send_shutdown_request(content, recipient)
        elif type == "shutdown_response":
            return await self._send_shutdown_response(content, recipient, approve, request_id)
        elif type == "plan_approval_response":
            return await self._send_plan_approval_response(content, recipient, approve, request_id)
        return f"Unknown message type: {type}"

    async def _send_direct(self, content: str, recipient: str | None, summary: str | None) -> str:
        if not recipient:
            return "Error: recipient is required for message type"

        entry = await self._agent_registry.get_by_name(recipient)
        if not entry:
            return f"Error: agent '{recipient}' not found"

        msg = _format_agent_message(
            "message", content,
            sender_thread=self._current_thread_id,
            summary=summary,
        )
        self._queue_manager.enqueue(msg, entry.thread_id, "agent_message")
        return f"Message sent to {recipient}"

    async def _send_broadcast(self, content: str, summary: str | None) -> str:
        agents = await self._agent_registry.list_running()
        targets = [a for a in agents if a.thread_id != self._current_thread_id]

        for agent in targets:
            msg = _format_agent_message(
                "broadcast", content,
                sender_thread=self._current_thread_id,
                summary=summary,
            )
            self._queue_manager.enqueue(msg, agent.thread_id, "agent_message")

        return f"Broadcast sent to {len(targets)} agents"

    async def _send_shutdown_request(self, content: str, recipient: str | None) -> str:
        if not recipient:
            return "Error: recipient required for shutdown_request"

        entry = await self._agent_registry.get_by_name(recipient)
        if not entry:
            return f"Error: agent '{recipient}' not found"

        msg = _format_agent_message(
            "shutdown_request", content,
            sender_thread=self._current_thread_id,
        )
        self._queue_manager.enqueue(msg, entry.thread_id, "agent_message")
        return f"Shutdown request sent to {recipient}"

    async def _send_shutdown_response(
        self, content: str, recipient: str | None, approve: bool | None, request_id: str | None
    ) -> str:
        if recipient:
            entry = await self._agent_registry.get_by_name(recipient)
            if not entry:
                return f"Error: agent '{recipient}' not found"
            target_thread = entry.thread_id
        else:
            return "Error: recipient required for shutdown_response"

        msg = _format_agent_message(
            "shutdown_response", content,
            sender_thread=self._current_thread_id,
            approve=approve,
            request_id=request_id,
        )
        self._queue_manager.enqueue(msg, target_thread, "agent_message")
        return f"Shutdown response sent to {recipient}"

    async def _send_plan_approval_response(
        self, content: str, recipient: str | None, approve: bool | None, request_id: str | None
    ) -> str:
        if not recipient:
            return "Error: recipient required for plan_approval_response"

        entry = await self._agent_registry.get_by_name(recipient)
        if not entry:
            return f"Error: agent '{recipient}' not found"

        msg = _format_agent_message(
            "plan_approval_response", content,
            sender_thread=self._current_thread_id,
            approve=approve,
            request_id=request_id,
        )
        self._queue_manager.enqueue(msg, entry.thread_id, "agent_message")
        action = "approved" if approve else "rejected"
        return f"Plan {action} — response sent to {recipient}"
