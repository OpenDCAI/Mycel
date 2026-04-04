from __future__ import annotations


def is_terminal_background_notification(
    content: str | None,
    *,
    source: str | None,
    notification_type: str | None,
) -> bool:
    if source != "system" or notification_type not in {"agent", "command"}:
        return False
    text = content or ""
    return "<task-notification>" in text or "<CommandNotification>" in text
