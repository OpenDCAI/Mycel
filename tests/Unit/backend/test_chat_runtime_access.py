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


def test_runtime_access_reads_chat_runtime_state_bundle():
    messaging_service = object()
    typing_tracker = object()
    relationship_service = object()
    contact_repo = object()

    app = _app_state(
        chat_runtime_state=SimpleNamespace(
            messaging_service=messaging_service,
            typing_tracker=typing_tracker,
            relationship_service=relationship_service,
            contact_repo=contact_repo,
        )
    )

    assert chat_runtime_access.get_messaging_service(app) is messaging_service
    assert chat_runtime_access.get_optional_messaging_service(app) is messaging_service
    assert chat_runtime_access.get_typing_tracker(app) is typing_tracker
    assert chat_runtime_access.get_relationship_service(app) is relationship_service
    assert chat_runtime_access.get_contact_repo(app) is contact_repo


def test_runtime_access_does_not_fall_back_to_legacy_chat_attrs():
    app = _app_state(
        messaging_service=object(),
        typing_tracker=object(),
        relationship_service=object(),
        contact_repo=object(),
    )

    with pytest.raises(RuntimeError, match="chat bootstrap not attached: messaging_service"):
        chat_runtime_access.get_messaging_service(app)
    assert chat_runtime_access.get_optional_messaging_service(app) is None

    with pytest.raises(RuntimeError, match="chat bootstrap not attached: typing_tracker"):
        chat_runtime_access.get_typing_tracker(app)

    with pytest.raises(RuntimeError, match="chat bootstrap not attached: relationship_service"):
        chat_runtime_access.get_relationship_service(app)

    with pytest.raises(RuntimeError, match="chat bootstrap not attached: contact_repo"):
        chat_runtime_access.get_contact_repo(app)
