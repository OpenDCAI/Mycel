"""Chat-owned transport implementations for delivery into Agent Runtime."""

from __future__ import annotations

import asyncio

import httpx

from protocols.agent_runtime import (
    AgentChatDeliveryEnvelope,
    AgentRuntimeGateway,
    ChatDeliveryTransport,
    chat_delivery_envelope_to_payload,
)


class InProcessChatRuntimeTransport:
    """Bridge a sync chat delivery callback into the native async gateway."""

    def __init__(self, *, runtime_gateway: AgentRuntimeGateway, loop: asyncio.AbstractEventLoop) -> None:
        if runtime_gateway is None:
            raise RuntimeError("Agent runtime gateway is not configured")
        self._runtime_gateway = runtime_gateway
        self._loop = loop

    def deliver_chat(self, envelope: AgentChatDeliveryEnvelope) -> None:
        future = asyncio.run_coroutine_threadsafe(self._runtime_gateway.dispatch_chat(envelope), self._loop)
        future.result()


class HttpChatRuntimeTransport:
    """Post chat delivery envelopes to a remote Threads backend ingress."""

    def __init__(self, *, base_url: str, timeout: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def deliver_chat(self, envelope: AgentChatDeliveryEnvelope) -> None:
        with httpx.Client(timeout=self._timeout, trust_env=False) as client:
            response = client.post(
                f"{self._base_url}/api/internal/agent-runtime/chat-deliveries",
                json=chat_delivery_envelope_to_payload(envelope),
            )
            response.raise_for_status()


def build_inprocess_chat_transport(
    *,
    runtime_gateway: AgentRuntimeGateway,
    loop: asyncio.AbstractEventLoop,
) -> ChatDeliveryTransport:
    return InProcessChatRuntimeTransport(runtime_gateway=runtime_gateway, loop=loop)


def build_http_chat_transport(*, base_url: str, timeout: float = 10.0) -> ChatDeliveryTransport:
    return HttpChatRuntimeTransport(base_url=base_url, timeout=timeout)
