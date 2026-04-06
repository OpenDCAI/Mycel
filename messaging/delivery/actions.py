"""Delivery action enum for messaging module."""

from __future__ import annotations

from enum import StrEnum


class DeliveryAction(StrEnum):
    DELIVER = "deliver"  # inject into agent context, wake agent
    NOTIFY = "notify"  # store + unread count, no delivery
    DROP = "drop"  # silent: stored but invisible to recipient
