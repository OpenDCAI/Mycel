from types import SimpleNamespace

import pytest

from backend.chat import runtime_access as chat_runtime_access


def _app_state(**kwargs):
    return SimpleNamespace(state=SimpleNamespace(**kwargs))


@pytest.mark.parametrize(
    ("getter_name", "detail"),
    [
        ("get_messaging_service", "chat bootstrap not attached: messaging_service"),
        ("get_typing_tracker", "chat bootstrap not attached: typing_tracker"),
        ("get_relationship_service", "chat bootstrap not attached: relationship_service"),
        ("get_contact_repo", "chat bootstrap not attached: contact_repo"),
    ],
)
def test_runtime_access_getters_fail_loud_when_chat_bootstrap_missing(getter_name: str, detail: str):
    getter = getattr(chat_runtime_access, getter_name)

    with pytest.raises(RuntimeError, match=detail):
        getter(_app_state())


def test_get_optional_typing_tracker_returns_none_when_missing():
    assert chat_runtime_access.get_optional_typing_tracker(_app_state()) is None
