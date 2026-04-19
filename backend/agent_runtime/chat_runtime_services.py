"""App-backed services for native Agent Runtime chat delivery."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Protocol


class AgentChatRuntimeServices(Protocol):
    def get_thread_by_user_id(self, recipient_user_id: str) -> dict[str, Any] | None: ...

    def list_threads_by_agent_user(self, agent_user_id: str) -> list[dict[str, Any]]: ...

    def iter_agent_pool_items(self) -> Iterable[tuple[str, Any]]: ...

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

    def __init__(self, app: Any) -> None:
        self._app = app

    def get_thread_by_user_id(self, recipient_user_id: str) -> dict[str, Any] | None:
        return self._app.state.thread_repo.get_by_user_id(recipient_user_id)

    def list_threads_by_agent_user(self, agent_user_id: str) -> list[dict[str, Any]]:
        return list(self._app.state.thread_repo.list_by_agent_user(agent_user_id))

    def iter_agent_pool_items(self) -> Iterable[tuple[str, Any]]:
        return self._app.state.agent_pool.items()

    async def get_or_create_thread_agent(self, thread_id: str) -> Any:
        from backend.web.services.agent_pool import get_or_create_agent, resolve_thread_sandbox
        from backend.web.services.streaming_service import _ensure_thread_handlers

        sandbox_type = resolve_thread_sandbox(self._app, thread_id)
        agent = await get_or_create_agent(self._app, sandbox_type, thread_id=thread_id)
        _ensure_thread_handlers(agent, thread_id, self._app)
        return agent

    def start_chat(self, thread_id: str, chat_id: str, recipient_user_id: str) -> None:
        typing_tracker = getattr(self._app.state, "typing_tracker", None)
        if typing_tracker is not None:
            typing_tracker.start_chat(thread_id, chat_id, recipient_user_id)

    def enqueue_chat_message(
        self,
        *,
        content: str,
        thread_id: str,
        sender_id: str,
        sender_name: str,
        sender_avatar_url: str | None,
    ) -> None:
        self._app.state.queue_manager.enqueue(
            content,
            thread_id,
            "chat",
            source="external",
            sender_id=sender_id,
            sender_name=sender_name,
            sender_avatar_url=sender_avatar_url,
        )
