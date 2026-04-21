from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.chat.api.http import dependencies as chat_dependencies


def _app_with_state(**state_kwargs):
    return SimpleNamespace(state=SimpleNamespace(**state_kwargs))


def test_require_messaging_service_returns_service() -> None:
    service = SimpleNamespace(name="messaging")

    result = chat_dependencies.get_messaging_service(_app_with_state(messaging_service=service))

    assert result is service


def test_require_messaging_service_raises_503_when_missing() -> None:
    with pytest.raises(HTTPException) as exc_info:
        chat_dependencies.get_messaging_service(_app_with_state())

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "MessagingService not initialized"


def test_require_chat_event_bus_raises_503_when_missing() -> None:
    with pytest.raises(HTTPException) as exc_info:
        chat_dependencies.get_chat_event_bus(_app_with_state())

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Chat event bus unavailable"


def test_require_relationship_service_raises_503_when_missing() -> None:
    with pytest.raises(HTTPException) as exc_info:
        chat_dependencies.get_relationship_service(_app_with_state())

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Relationship service unavailable"


def test_require_user_repo_raises_503_when_missing() -> None:
    with pytest.raises(HTTPException) as exc_info:
        chat_dependencies.get_user_repo(_app_with_state())

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "User repo unavailable"


def test_require_chat_repo_raises_503_when_missing() -> None:
    with pytest.raises(HTTPException) as exc_info:
        chat_dependencies.get_chat_repo(_app_with_state())

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Chat repo unavailable"


def test_require_thread_repo_raises_503_when_missing() -> None:
    with pytest.raises(HTTPException) as exc_info:
        chat_dependencies.get_thread_repo(_app_with_state())

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Thread repo unavailable"


def test_require_contact_repo_raises_503_when_missing() -> None:
    with pytest.raises(HTTPException) as exc_info:
        chat_dependencies.get_contact_repo(_app_with_state())

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Contact repo unavailable"


def test_require_runtime_thread_activity_reader_raises_503_when_missing() -> None:
    with pytest.raises(HTTPException) as exc_info:
        chat_dependencies.get_runtime_thread_activity_reader(_app_with_state())

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Thread activity reader unavailable"


def test_require_thread_last_active_map_raises_503_when_missing() -> None:
    with pytest.raises(HTTPException) as exc_info:
        chat_dependencies.get_thread_last_active_map(_app_with_state())

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Thread last-active map unavailable"
