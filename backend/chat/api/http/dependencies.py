"""Chat HTTP dependency helpers."""

from typing import Any

from fastapi import FastAPI, HTTPException, Request

from backend.identity.auth.user_resolution import get_current_user_id as resolve_current_user_id

get_current_user_id = resolve_current_user_id


async def get_app(request: Request) -> FastAPI:
    return request.app


def _require_state_attr(app: Any, attr_name: str, detail: str) -> Any:
    value = getattr(app.state, attr_name, None)
    if value is None:
        raise HTTPException(503, detail)
    return value


def get_messaging_service(app: Any) -> Any:
    return _require_state_attr(app, "messaging_service", "MessagingService not initialized")


def get_optional_messaging_service(app: Any) -> Any | None:
    return getattr(app.state, "messaging_service", None)


def get_relationship_service(app: Any) -> Any:
    return _require_state_attr(app, "relationship_service", "Relationship service unavailable")


def get_user_repo(app: Any) -> Any:
    return _require_state_attr(app, "user_repo", "User repo unavailable")


def get_thread_repo(app: Any) -> Any:
    return _require_state_attr(app, "thread_repo", "Thread repo unavailable")


def get_contact_repo(app: Any) -> Any:
    return _require_state_attr(app, "contact_repo", "Contact repo unavailable")


def get_chat_repo(app: Any) -> Any:
    return _require_state_attr(app, "chat_repo", "Chat repo unavailable")
