"""Agent runtime transport protocol contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True)
class AgentChatContext:
    chat_id: str
    title: str | None = None


@dataclass(frozen=True)
class AgentRuntimeActor:
    user_id: str
    user_type: str
    display_name: str
    avatar_url: str | None = None
    source: str | None = None


@dataclass(frozen=True)
class AgentChatRecipient:
    agent_user_id: str
    runtime_source: str
    thread_id: str | None = None


@dataclass(frozen=True)
class AgentRuntimeMessage:
    content: str
    content_type: str = "text"
    message_id: str | None = None
    signal: str | None = None
    created_at: str | None = None
    attachments: list[str] | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class AgentRuntimeTransport:
    delivery_id: str | None = None
    correlation_id: str | None = None
    idempotency_key: str | None = None


@dataclass(frozen=True)
class AgentChatDeliveryEnvelope:
    chat: AgentChatContext
    sender: AgentRuntimeActor
    recipient: AgentChatRecipient
    message: AgentRuntimeMessage
    wake: bool = True
    transport: AgentRuntimeTransport = AgentRuntimeTransport()
    protocol_version: Literal["agent.chat.delivery.v1"] = "agent.chat.delivery.v1"
    event_type: Literal["chat.message"] = "chat.message"
    extensions: dict[str, Any] | None = None


@dataclass(frozen=True)
class AgentThreadInputEnvelope:
    thread_id: str
    sender: AgentRuntimeActor
    message: AgentRuntimeMessage
    transport: AgentRuntimeTransport = AgentRuntimeTransport()
    enable_trajectory: bool = False
    protocol_version: Literal["agent.thread.input.v1"] = "agent.thread.input.v1"
    event_type: Literal["thread.input"] = "thread.input"


@dataclass(frozen=True)
class AgentChatDeliveryResult:
    status: Literal["accepted"]
    thread_id: str


@dataclass(frozen=True)
class AgentThreadInputResult:
    status: Literal["cancelled", "injected", "started"]
    routing: Literal["cancelled", "steer", "direct"]
    thread_id: str
    run_id: str | None = None

    def to_response(self) -> dict[str, str]:
        response = {"status": self.status, "routing": self.routing, "thread_id": self.thread_id}
        if self.run_id is not None:
            response["run_id"] = self.run_id
        return response
