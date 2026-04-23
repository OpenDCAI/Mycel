"""Threads-owned transport implementations for owner/thread input dispatch."""

from __future__ import annotations

import httpx

from protocols.agent_runtime import (
    AgentRuntimeGateway,
    AgentThreadInputEnvelope,
    AgentThreadInputResult,
    ThreadInputTransport,
    thread_input_envelope_to_payload,
    thread_input_result_from_payload,
)


class InProcessThreadInputTransport:
    """Delegate thread input dispatch to the native in-process gateway."""

    def __init__(self, *, runtime_gateway: AgentRuntimeGateway) -> None:
        if runtime_gateway is None:
            raise RuntimeError("Agent runtime gateway is not configured")
        self._runtime_gateway = runtime_gateway

    async def dispatch_thread_input(self, envelope: AgentThreadInputEnvelope) -> AgentThreadInputResult:
        return await self._runtime_gateway.dispatch_thread_input(envelope)


class HttpThreadInputTransport:
    """Post thread-input envelopes to a remote Threads backend ingress."""

    def __init__(self, *, base_url: str, timeout: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def dispatch_thread_input(self, envelope: AgentThreadInputEnvelope) -> AgentThreadInputResult:
        async with httpx.AsyncClient(timeout=self._timeout, trust_env=False) as client:
            response = await client.post(
                f"{self._base_url}/api/internal/agent-runtime/thread-input",
                json=thread_input_envelope_to_payload(envelope),
            )
            response.raise_for_status()
            return thread_input_result_from_payload(response.json())


def build_inprocess_thread_input_transport(*, runtime_gateway: AgentRuntimeGateway) -> ThreadInputTransport:
    return InProcessThreadInputTransport(runtime_gateway=runtime_gateway)


def build_http_thread_input_transport(*, base_url: str, timeout: float = 10.0) -> ThreadInputTransport:
    return HttpThreadInputTransport(base_url=base_url, timeout=timeout)
