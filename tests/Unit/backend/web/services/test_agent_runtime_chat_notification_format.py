from __future__ import annotations

from backend.agent_runtime.chat_notification_format import format_chat_notification


def test_chat_notification_format_includes_explicit_read_and_reply_instructions() -> None:
    result = format_chat_notification(
        sender_name="alice",
        chat_id="chat-123",
        unread_count=2,
    )

    assert 'read_messages(chat_id="chat-123")' in result
    assert 'Do not call send_message(chat_id="chat-123", ...) before read_messages(chat_id="chat-123") succeeds.' in result
    assert 'send_message(chat_id="chat-123", content="...")' in result
    assert "Prefer using this exact chat_id directly" in result
    assert "Do not treat your normal assistant text as a chat reply." in result
