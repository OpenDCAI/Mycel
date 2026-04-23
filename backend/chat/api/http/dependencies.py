"""Chat HTTP dependency helpers."""

from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Request

from backend.chat import runtime_access as chat_runtime_access
from backend.identity.auth.user_resolution import get_current_user_id as resolve_current_user_id
from backend.threads.owner_reads import list_owner_thread_rows_for_auth_burst
from protocols.identity_read import UserDirectory

get_current_user_id = resolve_current_user_id


async def get_app(request: Request) -> FastAPI:
    return request.app


def _require_state_attr(app: Any, attr_name: str, detail: str) -> Any:
    value = getattr(app.state, attr_name, None)
    if value is None:
        raise HTTPException(503, detail)
    return value


def get_messaging_service(app: Annotated[Any, Depends(get_app)]) -> Any:
    # @@@chat-http-runtime-bundle-only - chat HTTP dependency helpers should
    # read chat-owned services from the bundled chat_runtime_state instead of
    # falling back to loose app.state attrs.
    runtime_state = _require_state_attr(app, "chat_runtime_state", "MessagingService not initialized")
    return runtime_state.messaging_service


def get_relationship_service(app: Annotated[Any, Depends(get_app)]) -> Any:
    runtime_state = _require_state_attr(app, "chat_runtime_state", "Relationship service unavailable")
    return runtime_state.relationship_service


def get_user_directory(app: Annotated[Any, Depends(get_app)]) -> UserDirectory:
    runtime_state = _require_state_attr(app, "auth_runtime_state", "User directory unavailable")
    return runtime_state.user_directory


def get_user_repo(app: Annotated[Any, Depends(get_app)]) -> Any:
    return _require_state_attr(app, "user_repo", "User repo unavailable")


def get_thread_repo(app: Annotated[Any, Depends(get_app)]) -> Any:
    return _require_state_attr(app, "thread_repo", "Thread repo unavailable")


def get_contact_repo(app: Annotated[Any, Depends(get_app)]) -> Any:
    runtime_state = _require_state_attr(app, "chat_runtime_state", "Contact repo unavailable")
    return runtime_state.contact_repo


def get_chat_repo(app: Annotated[Any, Depends(get_app)]) -> Any:
    runtime_state = _require_state_attr(app, "chat_runtime_state", "Chat repo unavailable")
    return runtime_state.chat_repo


def get_chat_event_bus(app: Annotated[Any, Depends(get_app)]) -> Any:
    runtime_state = _require_state_attr(app, "chat_runtime_state", "Chat event bus unavailable")
    return runtime_state.chat_event_bus


def get_typing_tracker(app: Annotated[Any, Depends(get_app)]) -> Any:
    try:
        return chat_runtime_access.get_typing_tracker(app)
    except RuntimeError as exc:
        raise HTTPException(503, "Typing tracker unavailable") from exc


def get_hire_conversation_reader(app: Annotated[Any, Depends(get_app)]) -> Any:
    try:
        return chat_runtime_access.get_hire_conversation_reader(app)
    except RuntimeError as exc:
        raise HTTPException(503, "Hire conversation reader unavailable") from exc


def get_agent_actor_lookup(app: Annotated[Any, Depends(get_app)]) -> Any:
    try:
        return chat_runtime_access.get_agent_actor_lookup(app)
    except RuntimeError as exc:
        raise HTTPException(503, "Agent actor lookup unavailable") from exc


def get_runtime_thread_activity_reader(app: Annotated[Any, Depends(get_app)]) -> Any:
    runtime_state = _require_state_attr(app, "threads_runtime_state", "Thread activity reader unavailable")
    return runtime_state.activity_reader


def get_thread_last_active_map(app: Annotated[Any, Depends(get_app)]) -> Any:
    return _require_state_attr(app, "thread_last_active", "Thread last-active map unavailable")


def get_owner_thread_rows_loader(app: Annotated[Any, Depends(get_app)]) -> Callable[[str], Awaitable[list[dict[str, Any]]]]:
    async def _load(user_id: str) -> list[dict[str, Any]]:
        return await list_owner_thread_rows_for_auth_burst(app, user_id)

    return _load
