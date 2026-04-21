"""Fail-loud outbound runtime accessors for chat-owned state."""

from __future__ import annotations

from typing import Any


def _require_chat_state(app: Any, attr_name: str) -> Any:
    runtime_state = getattr(app.state, "chat_runtime_state", None)
    value = getattr(runtime_state, attr_name, None) if runtime_state is not None else getattr(app.state, attr_name, None)
    if value is None:
        raise RuntimeError(f"chat bootstrap not attached: {attr_name}")
    return value


def get_messaging_service(app: Any) -> Any:
    return _require_chat_state(app, "messaging_service")


def get_optional_messaging_service(app: Any) -> Any | None:
    runtime_state = getattr(app.state, "chat_runtime_state", None)
    if runtime_state is not None:
        return getattr(runtime_state, "messaging_service", None)
    return getattr(app.state, "messaging_service", None)


def get_typing_tracker(app: Any) -> Any:
    return _require_chat_state(app, "typing_tracker")


def get_optional_typing_tracker(app: Any) -> Any | None:
    runtime_state = getattr(app.state, "chat_runtime_state", None)
    if runtime_state is not None:
        return getattr(runtime_state, "typing_tracker", None)
    return getattr(app.state, "typing_tracker", None)


def get_relationship_service(app: Any) -> Any:
    return _require_chat_state(app, "relationship_service")


def get_contact_repo(app: Any) -> Any:
    return _require_chat_state(app, "contact_repo")
