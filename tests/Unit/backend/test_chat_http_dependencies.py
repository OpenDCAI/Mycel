from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.chat.api.http import dependencies as chat_http_dependencies


def _app_state(**kwargs):
    return SimpleNamespace(state=SimpleNamespace(**kwargs))


def test_get_messaging_service_returns_service_when_present():
    service = SimpleNamespace(name="messaging")

    assert chat_http_dependencies.get_messaging_service(_app_state(messaging_service=service)) is service


@pytest.mark.asyncio
async def test_get_owner_thread_rows_loader_binds_app() -> None:
    seen: list[tuple[object, str]] = []

    async def _fake_list_owner_thread_rows_for_auth_burst(app, user_id: str):
        seen.append((app, user_id))
        return [{"id": "thread-1"}]

    app = _app_state(thread_repo=SimpleNamespace())
    original = chat_http_dependencies.list_owner_thread_rows_for_auth_burst
    chat_http_dependencies.list_owner_thread_rows_for_auth_burst = _fake_list_owner_thread_rows_for_auth_burst
    try:
        loader = chat_http_dependencies.get_owner_thread_rows_loader(app)
        result = await loader("owner-1")
    finally:
        chat_http_dependencies.list_owner_thread_rows_for_auth_burst = original

    assert result == [{"id": "thread-1"}]
    assert seen == [(app, "owner-1")]


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


def test_get_runtime_thread_activity_reader_fails_loud_when_missing():
    with pytest.raises(HTTPException) as exc_info:
        chat_http_dependencies.get_runtime_thread_activity_reader(_app_state())

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Thread activity reader unavailable"


def test_get_runtime_thread_activity_reader_reads_threads_runtime_state():
    activity_reader = object()

    app = _app_state(threads_runtime_state=SimpleNamespace(activity_reader=activity_reader))

    assert chat_http_dependencies.get_runtime_thread_activity_reader(app) is activity_reader


@pytest.mark.parametrize(
    ("getter_name", "detail"),
    [
        ("get_user_repo", "User repo unavailable"),
        ("get_thread_repo", "Thread repo unavailable"),
        ("get_contact_repo", "Contact repo unavailable"),
        ("get_chat_repo", "Chat repo unavailable"),
        ("get_chat_event_bus", "Chat event bus unavailable"),
        ("get_thread_last_active_map", "Thread last-active map unavailable"),
    ],
)
def test_repo_getters_fail_loud_when_missing(getter_name: str, detail: str):
    getter = getattr(chat_http_dependencies, getter_name)

    with pytest.raises(HTTPException) as exc_info:
        getter(_app_state())

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == detail
