from __future__ import annotations

from enum import StrEnum


class WakeSafety(StrEnum):
    ALLOWED = "allowed"
    BLOCKED = "blocked"


class SenderWakeScope(StrEnum):
    OPEN = "open"
    TARGETED = "targeted"
    QUIET = "quiet"

    @classmethod
    def from_mentions(cls, mentions: list[str]) -> SenderWakeScope:
        return cls.TARGETED if mentions else cls.OPEN


class ReceiverWakePreference(StrEnum):
    ALWAYS_WAKE = "always_wake"
    DEFAULT = "default"
    QUIET = "quiet"


class WakeAction(StrEnum):
    WAKE_NOW = "wake_now"
    QUEUE_ONLY = "queue_only"
    DROP_RUNTIME = "drop_runtime"


def compose_wake_action(
    *,
    safety: WakeSafety,
    sender_scope: SenderWakeScope,
    receiver_preference: ReceiverWakePreference,
    recipient_is_mentioned: bool,
) -> WakeAction:
    if safety is WakeSafety.BLOCKED:
        return WakeAction.DROP_RUNTIME
    if receiver_preference is ReceiverWakePreference.QUIET:
        return WakeAction.QUEUE_ONLY
    if receiver_preference is ReceiverWakePreference.ALWAYS_WAKE:
        return WakeAction.WAKE_NOW
    if sender_scope is SenderWakeScope.QUIET:
        return WakeAction.QUEUE_ONLY
    if sender_scope is SenderWakeScope.OPEN:
        return WakeAction.WAKE_NOW
    if recipient_is_mentioned:
        return WakeAction.WAKE_NOW
    return WakeAction.QUEUE_ONLY
