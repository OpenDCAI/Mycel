"""Agent runtime transport protocol contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any, Literal, Protocol


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


class AgentRuntimeGateway(Protocol):
    async def dispatch_chat(self, envelope: AgentChatDeliveryEnvelope) -> AgentChatDeliveryResult: ...

    async def dispatch_thread_input(self, envelope: AgentThreadInputEnvelope) -> AgentThreadInputResult: ...


class ThreadInputTransport(Protocol):
    async def dispatch_thread_input(self, envelope: AgentThreadInputEnvelope) -> AgentThreadInputResult: ...


class ChatDeliveryTransport(Protocol):
    def deliver_chat(self, envelope: AgentChatDeliveryEnvelope) -> None: ...


def _transport_from_payload(payload: Mapping[str, Any] | None) -> AgentRuntimeTransport:
    data = payload or {}
    return AgentRuntimeTransport(
        delivery_id=data.get("delivery_id"),
        correlation_id=data.get("correlation_id"),
        idempotency_key=data.get("idempotency_key"),
    )


def chat_delivery_envelope_to_payload(envelope: AgentChatDeliveryEnvelope) -> dict[str, Any]:
    return asdict(envelope)


def chat_delivery_envelope_from_payload(payload: Mapping[str, Any]) -> AgentChatDeliveryEnvelope:
    chat = payload["chat"]
    sender = payload["sender"]
    recipient = payload["recipient"]
    message = payload["message"]
    return AgentChatDeliveryEnvelope(
        chat=AgentChatContext(
            chat_id=chat["chat_id"],
            title=chat.get("title"),
        ),
        sender=AgentRuntimeActor(
            user_id=sender["user_id"],
            user_type=sender["user_type"],
            display_name=sender["display_name"],
            avatar_url=sender.get("avatar_url"),
            source=sender.get("source"),
        ),
        recipient=AgentChatRecipient(
            agent_user_id=recipient["agent_user_id"],
            runtime_source=recipient["runtime_source"],
        ),
        message=AgentRuntimeMessage(
            content=message["content"],
            content_type=message.get("content_type", "text"),
            message_id=message.get("message_id"),
            signal=message.get("signal"),
            created_at=message.get("created_at"),
            attachments=message.get("attachments"),
            metadata=message.get("metadata"),
        ),
        transport=_transport_from_payload(payload.get("transport")),
        protocol_version=payload.get("protocol_version", "agent.chat.delivery.v1"),
        event_type=payload.get("event_type", "chat.message"),
        extensions=payload.get("extensions"),
    )


def chat_delivery_result_to_payload(result: AgentChatDeliveryResult) -> dict[str, Any]:
    return asdict(result)


def thread_input_envelope_to_payload(envelope: AgentThreadInputEnvelope) -> dict[str, Any]:
    return asdict(envelope)


def thread_input_envelope_from_payload(payload: Mapping[str, Any]) -> AgentThreadInputEnvelope:
    sender = payload["sender"]
    message = payload["message"]
    return AgentThreadInputEnvelope(
        thread_id=payload["thread_id"],
        sender=AgentRuntimeActor(
            user_id=sender["user_id"],
            user_type=sender["user_type"],
            display_name=sender["display_name"],
            avatar_url=sender.get("avatar_url"),
            source=sender.get("source"),
        ),
        message=AgentRuntimeMessage(
            content=message["content"],
            content_type=message.get("content_type", "text"),
            message_id=message.get("message_id"),
            signal=message.get("signal"),
            created_at=message.get("created_at"),
            attachments=message.get("attachments"),
            metadata=message.get("metadata"),
        ),
        transport=_transport_from_payload(payload.get("transport")),
        enable_trajectory=payload.get("enable_trajectory", False),
        protocol_version=payload.get("protocol_version", "agent.thread.input.v1"),
        event_type=payload.get("event_type", "thread.input"),
    )


def thread_input_result_to_payload(result: AgentThreadInputResult) -> dict[str, Any]:
    return asdict(result)


def thread_input_result_from_payload(payload: Mapping[str, Any]) -> AgentThreadInputResult:
    return AgentThreadInputResult(
        status=payload["status"],
        routing=payload["routing"],
        thread_id=payload["thread_id"],
        run_id=payload.get("run_id"),
    )
