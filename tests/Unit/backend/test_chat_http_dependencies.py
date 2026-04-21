from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.chat.api.http import dependencies as chat_http_dependencies


def _app_state(**kwargs):
    return SimpleNamespace(state=SimpleNamespace(**kwargs))


def test_get_messaging_service_fails_loud_when_missing():
    with pytest.raises(HTTPException) as exc_info:
        chat_http_dependencies.get_messaging_service(_app_state())

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "MessagingService not initialized"


def test_get_relationship_service_fails_loud_when_missing():
    with pytest.raises(HTTPException) as exc_info:
        chat_http_dependencies.get_relationship_service(_app_state())

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Relationship service unavailable"


@pytest.mark.parametrize(
    ("getter_name", "detail"),
    [
        ("get_user_repo", "User repo unavailable"),
        ("get_thread_repo", "Thread repo unavailable"),
        ("get_contact_repo", "Contact repo unavailable"),
        ("get_chat_repo", "Chat repo unavailable"),
    ],
)
def test_repo_getters_fail_loud_when_missing(getter_name: str, detail: str):
    getter = getattr(chat_http_dependencies, getter_name)

    with pytest.raises(HTTPException) as exc_info:
        getter(_app_state())

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == detail
