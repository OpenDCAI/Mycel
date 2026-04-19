"""Bootstrap helpers for binding the Agent Runtime Gateway to app-backed handlers."""

from __future__ import annotations

from typing import Any

from backend.agent_runtime.chat_handler import NativeAgentChatDeliveryHandler
from backend.agent_runtime.chat_runtime_services import AppAgentChatRuntimeServices
from backend.agent_runtime.gateway import NativeAgentRuntimeGateway
from backend.agent_runtime.thread_handler import NativeAgentThreadInputHandler


def build_agent_runtime_gateway(app: Any) -> NativeAgentRuntimeGateway:
    return NativeAgentRuntimeGateway(
        chat_handlers={
            "mycel": NativeAgentChatDeliveryHandler(
                runtime_services=AppAgentChatRuntimeServices(app),
            )
        },
        thread_input_handler=NativeAgentThreadInputHandler(app),
    )
