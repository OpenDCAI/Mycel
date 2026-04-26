from __future__ import annotations


def format_chat_notification(sender_name: str, chat_id: str, unread_count: int, signal: str | None = None) -> str:
    """Lightweight notification — agent must read_messages to see content.

    @@@v3-notification-only - no message content injected. Agent calls
    read_messages(chat_id=...) to read, then send_message() to reply.
    """
    signal_hint = f" [signal: {signal}]" if signal and signal != "open" else ""
    return (
        "<system-reminder>\n"
        f"New message from {sender_name} in chat {chat_id} ({unread_count} unread).{signal_hint}\n"
        f'Read it with read_messages(chat_id="{chat_id}").\n'
        f'Do not call send_message(chat_id="{chat_id}", ...) before read_messages(chat_id="{chat_id}") succeeds.\n'
        f'Reply with send_message(chat_id="{chat_id}", content="...").\n'
        "Prefer using this exact chat_id directly.\n"
        "Do not treat your normal assistant text as a chat reply.\n"
        "</system-reminder>"
    )
