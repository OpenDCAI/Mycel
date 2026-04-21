"""App-backed services for native Agent Runtime chat delivery."""

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
    """Runtime-owned adapter around app-backed chat delivery dependencies."""

    def __init__(self, app: Any, *, typing_tracker: Any, queue_manager: Any) -> None:
        self._app = app
        self._typing_tracker = typing_tracker
        self._queue_manager = queue_manager

    async def get_or_create_thread_agent(self, thread_id: str) -> Any:
        from backend.threads.activity_pool_service import get_or_create_agent, resolve_thread_sandbox
        from backend.threads.streaming import _ensure_thread_handlers

        sandbox_type = resolve_thread_sandbox(self._app, thread_id)
        agent = await get_or_create_agent(self._app, sandbox_type, thread_id=thread_id)
        _ensure_thread_handlers(agent, thread_id, self._app)
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
