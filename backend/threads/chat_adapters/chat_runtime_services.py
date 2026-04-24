from __future__ import annotations

from typing import Any, Protocol


class AgentChatRuntimeServices(Protocol):
    async def get_or_create_thread_agent(self, thread_id: str) -> Any: ...

    def start_chat(self, thread_id: str, chat_id: str, recipient_user_id: str) -> None: ...

    def enqueue_chat_message(
        self,
        *,
        content: str,
        thread_id: str,
        sender_id: str,
        sender_name: str,
        sender_avatar_url: str | None,
    ) -> None: ...


class AppAgentChatRuntimeServices:
    def __init__(
        self,
        app: Any,
        *,
        typing_tracker: Any,
        queue_manager: Any,
        get_or_create_agent: Any,
        resolve_thread_sandbox: Any,
        ensure_thread_handlers: Any,
    ) -> None:
        self._app = app
        self._typing_tracker = typing_tracker
        self._queue_manager = queue_manager
        self._get_or_create_agent = get_or_create_agent
        self._resolve_thread_sandbox = resolve_thread_sandbox
        self._ensure_thread_handlers = ensure_thread_handlers

    async def get_or_create_thread_agent(self, thread_id: str) -> Any:
        sandbox_type = self._resolve_thread_sandbox(self._app, thread_id)
        agent = await self._get_or_create_agent(self._app, sandbox_type, thread_id=thread_id)
        self._ensure_thread_handlers(agent, thread_id, self._app)
        return agent

    def start_chat(self, thread_id: str, chat_id: str, recipient_user_id: str) -> None:
        self._typing_tracker.start_chat(thread_id, chat_id, recipient_user_id)

    def enqueue_chat_message(
        self,
        *,
        content: str,
        thread_id: str,
        sender_id: str,
        sender_name: str,
        sender_avatar_url: str | None,
    ) -> None:
        self._queue_manager.enqueue(
            content,
            thread_id,
            "chat",
            source="external",
            sender_id=sender_id,
            sender_name=sender_name,
            sender_avatar_url=sender_avatar_url,
        )
