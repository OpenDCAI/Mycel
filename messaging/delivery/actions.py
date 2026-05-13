"""Delivery action enum for messaging module."""

from __future__ import annotations

from enum import StrEnum


class DeliveryAction(StrEnum):
    DELIVER = "deliver"  # runtime delivery is allowed
    NOTIFY = "notify"  # runtime delivery is allowed without waking
    DROP = "drop"  # runtime delivery is blocked
