from __future__ import annotations

from types import SimpleNamespace

from messaging.service import MessagingService


def test_list_messages_by_time_range_normalizes_iso_timestamps_for_repo() -> None:
    captured: dict[str, object] = {}

    class _MessagesRepo:
        def list_by_time_range(self, chat_id: str, *, after=None, before=None):
            captured["chat_id"] = chat_id
            captured["after"] = after
            captured["before"] = before
            return []

    service = MessagingService(
        chat_repo=SimpleNamespace(),
        chat_member_repo=SimpleNamespace(),
        messages_repo=_MessagesRepo(),
        user_repo=SimpleNamespace(get_by_id=lambda _user_id: None),
    )

    service.list_messages_by_time_range(
        "chat-1",
        after="2026-04-22T10:59:37.792835+00:00",
        before="2026-04-22T11:59:37.792835+00:00",
    )

    assert captured["chat_id"] == "chat-1"
    assert isinstance(captured["after"], str)
    assert isinstance(captured["before"], str)
    assert "T" not in captured["after"]
    assert "T" not in captured["before"]
    assert "+" not in captured["after"]
    assert "+" not in captured["before"]
