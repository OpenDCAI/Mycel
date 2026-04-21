"""Chat HTTP dependency helpers."""

from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Request

from backend.identity.auth.user_resolution import get_current_user_id as resolve_current_user_id
from backend.threads.owner_reads import list_owner_thread_rows_for_auth_burst

get_current_user_id = resolve_current_user_id


async def get_app(request: Request) -> FastAPI:
    return request.app


def _require_state_attr(app: Any, attr_name: str, detail: str) -> Any:
    value = getattr(app.state, attr_name, None)
    if value is None:
        raise HTTPException(503, detail)
    return value


def get_messaging_service(app: Annotated[Any, Depends(get_app)]) -> Any:
    return _require_state_attr(app, "messaging_service", "MessagingService not initialized")


def get_optional_messaging_service(app: Annotated[Any, Depends(get_app)]) -> Any | None:
    return getattr(app.state, "messaging_service", None)


def get_relationship_service(app: Annotated[Any, Depends(get_app)]) -> Any:
    return _require_state_attr(app, "relationship_service", "Relationship service unavailable")


def get_user_repo(app: Annotated[Any, Depends(get_app)]) -> Any:
    return _require_state_attr(app, "user_repo", "User repo unavailable")


def get_thread_repo(app: Annotated[Any, Depends(get_app)]) -> Any:
    return _require_state_attr(app, "thread_repo", "Thread repo unavailable")


def get_contact_repo(app: Annotated[Any, Depends(get_app)]) -> Any:
    return _require_state_attr(app, "contact_repo", "Contact repo unavailable")


def get_chat_repo(app: Annotated[Any, Depends(get_app)]) -> Any:
    return _require_state_attr(app, "chat_repo", "Chat repo unavailable")


def get_chat_event_bus(app: Annotated[Any, Depends(get_app)]) -> Any:
    return _require_state_attr(app, "chat_event_bus", "Chat event bus unavailable")


def get_runtime_thread_activity_reader(app: Annotated[Any, Depends(get_app)]) -> Any:
    runtime_state = _require_state_attr(app, "threads_runtime_state", "Thread activity reader unavailable")
    return runtime_state.activity_reader


def get_thread_last_active_map(app: Annotated[Any, Depends(get_app)]) -> Any:
    return _require_state_attr(app, "thread_last_active", "Thread last-active map unavailable")


def get_owner_thread_rows_loader(app: Annotated[Any, Depends(get_app)]) -> Callable[[str], Awaitable[list[dict[str, Any]]]]:
    async def _load(user_id: str) -> list[dict[str, Any]]:
        return await list_owner_thread_rows_for_auth_burst(app, user_id)

    return _load
