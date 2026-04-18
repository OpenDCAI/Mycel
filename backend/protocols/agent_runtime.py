"""Agent runtime transport protocol contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True)
class AgentChatContext:
    chat_id: str
    title: str | None = None


@dataclass(frozen=True)
class AgentChatActor:
    user_id: str
    user_type: str
    display_name: str
    avatar_url: str | None = None


@dataclass(frozen=True)
class AgentChatRecipient:
    agent_user_id: str
    runtime_source: str


@dataclass(frozen=True)
class AgentChatMessage:
    content: str
    content_type: str = "text"
    message_id: str | None = None
    signal: str | None = None
    created_at: str | None = None


@dataclass(frozen=True)
class AgentChatTransport:
    delivery_id: str | None = None
    correlation_id: str | None = None
    idempotency_key: str | None = None


@dataclass(frozen=True)
class AgentChatDeliveryEnvelope:
    chat: AgentChatContext
    sender: AgentChatActor
    recipient: AgentChatRecipient
    message: AgentChatMessage
    transport: AgentChatTransport = AgentChatTransport()
    protocol_version: Literal["agent.chat.delivery.v1"] = "agent.chat.delivery.v1"
    event_type: Literal["chat.message"] = "chat.message"
    extensions: dict[str, Any] | None = None


@dataclass(frozen=True)
class AgentThreadInputEnvelope:
    thread_id: str
    content: str
    source: str = "owner"
    enable_trajectory: bool = False
    sender_name: str | None = None
    sender_avatar_url: str | None = None
    attachments: list[str] | None = None
    message_metadata: dict[str, Any] | None = None
    protocol_version: Literal["agent.thread.input.v1"] = "agent.thread.input.v1"
    event_type: Literal["thread.input"] = "thread.input"


@dataclass(frozen=True)
class AgentGatewayDeliveryResult:
    status: Literal["accepted", "skipped"]
    thread_id: str | None
    reason: str | None = None
