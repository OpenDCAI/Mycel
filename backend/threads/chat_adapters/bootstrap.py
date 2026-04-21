"""Bootstrap helpers for binding the Agent Runtime Gateway to app-backed handlers."""

from __future__ import annotations

from typing import Any

from backend.threads.chat_adapters.chat_handler import NativeAgentChatDeliveryHandler
from backend.threads.chat_adapters.chat_runtime_services import AppAgentChatRuntimeServices
from backend.threads.chat_adapters.gateway import NativeAgentRuntimeGateway
from backend.threads.chat_adapters.activity_reader import AppRuntimeThreadActivityReader
from backend.threads.chat_adapters.thread_handler import NativeAgentThreadInputHandler


def build_agent_runtime_gateway(app: Any) -> NativeAgentRuntimeGateway:
    app.state.agent_runtime_thread_activity_reader = AppRuntimeThreadActivityReader(app)
    return NativeAgentRuntimeGateway(
        chat_handlers={
            "mycel": NativeAgentChatDeliveryHandler(
                runtime_services=AppAgentChatRuntimeServices(app),
            )
        },
        thread_input_handler=NativeAgentThreadInputHandler(app),
    )
