from __future__ import annotations

from backend.threads.chat_adapters.chat_runtime_services import AgentChatRuntimeServices
from protocols import agent_runtime as agent_runtime_protocol


class NativeAgentChatDeliveryHandler:
    def __init__(
        self,
        *,
        runtime_services: AgentChatRuntimeServices,
    ) -> None:
        self._runtime_services = runtime_services

    async def dispatch(self, envelope: agent_runtime_protocol.AgentChatDeliveryEnvelope) -> agent_runtime_protocol.AgentChatDeliveryResult:
        from langchain_core.runnables.config import var_child_runnable_config  # pyright: ignore[reportMissingImports]

        var_child_runnable_config.set(None)

        thread_id = envelope.recipient.thread_id
        if not thread_id:
            raise RuntimeError(f"Agent chat recipient has no runtime thread: {envelope.recipient.agent_user_id}")
        await self._runtime_services.get_or_create_thread_agent(thread_id)
        self._runtime_services.start_chat(thread_id, envelope.chat.chat_id, envelope.recipient.agent_user_id)
        self._runtime_services.enqueue_chat_message(
            content=envelope.message.content,
            thread_id=thread_id,
            sender_id=envelope.sender.user_id,
            sender_name=envelope.sender.display_name,
            sender_avatar_url=envelope.sender.avatar_url,
        )
        return agent_runtime_protocol.AgentChatDeliveryResult(status="accepted", thread_id=thread_id)
