from messaging.delivery.wake_policy import (
    ReceiverWakePreference,
    SenderWakeScope,
    WakeAction,
    WakeSafety,
    compose_wake_action,
)


def test_sender_scope_is_open_without_mentions() -> None:
    assert SenderWakeScope.from_mentions([]) is SenderWakeScope.OPEN


def test_sender_scope_is_targeted_with_mentions() -> None:
    assert SenderWakeScope.from_mentions(["agent-user-1"]) is SenderWakeScope.TARGETED


def test_default_receiver_wakes_for_open_sender_scope() -> None:
    action = compose_wake_action(
        safety=WakeSafety.ALLOWED,
        sender_scope=SenderWakeScope.OPEN,
        receiver_preference=ReceiverWakePreference.DEFAULT,
        recipient_is_mentioned=False,
    )

    assert action is WakeAction.WAKE_NOW


def test_default_receiver_queues_when_targeted_but_unmentioned() -> None:
    action = compose_wake_action(
        safety=WakeSafety.ALLOWED,
        sender_scope=SenderWakeScope.TARGETED,
        receiver_preference=ReceiverWakePreference.DEFAULT,
        recipient_is_mentioned=False,
    )

    assert action is WakeAction.QUEUE_ONLY


def test_default_receiver_wakes_when_targeted_and_mentioned() -> None:
    action = compose_wake_action(
        safety=WakeSafety.ALLOWED,
        sender_scope=SenderWakeScope.TARGETED,
        receiver_preference=ReceiverWakePreference.DEFAULT,
        recipient_is_mentioned=True,
    )

    assert action is WakeAction.WAKE_NOW


def test_quiet_receiver_queues_even_when_mentioned() -> None:
    action = compose_wake_action(
        safety=WakeSafety.ALLOWED,
        sender_scope=SenderWakeScope.TARGETED,
        receiver_preference=ReceiverWakePreference.QUIET,
        recipient_is_mentioned=True,
    )

    assert action is WakeAction.QUEUE_ONLY


def test_always_wake_receiver_wakes_even_when_unmentioned() -> None:
    action = compose_wake_action(
        safety=WakeSafety.ALLOWED,
        sender_scope=SenderWakeScope.TARGETED,
        receiver_preference=ReceiverWakePreference.ALWAYS_WAKE,
        recipient_is_mentioned=False,
    )

    assert action is WakeAction.WAKE_NOW


def test_blocked_safety_drops_runtime_notification() -> None:
    action = compose_wake_action(
        safety=WakeSafety.BLOCKED,
        sender_scope=SenderWakeScope.OPEN,
        receiver_preference=ReceiverWakePreference.ALWAYS_WAKE,
        recipient_is_mentioned=True,
    )

    assert action is WakeAction.DROP_RUNTIME
