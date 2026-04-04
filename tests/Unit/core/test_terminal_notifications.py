from core.runtime.notifications import is_terminal_background_notification


def test_is_terminal_background_notification_accepts_system_terminal_markers():
    assert (
        is_terminal_background_notification(
            "<task-notification>done</task-notification>",
            source="system",
            notification_type="agent",
        )
        is True
    )
    assert (
        is_terminal_background_notification(
            "<CommandNotification>done</CommandNotification>",
            source="system",
            notification_type="command",
        )
        is True
    )


def test_is_terminal_background_notification_rejects_non_system_or_non_terminal_messages():
    assert (
        is_terminal_background_notification(
            "<task-notification>done</task-notification>",
            source="owner",
            notification_type="agent",
        )
        is False
    )
    assert (
        is_terminal_background_notification(
            "plain reminder",
            source="system",
            notification_type="agent",
        )
        is False
    )
