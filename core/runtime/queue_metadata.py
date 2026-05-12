from __future__ import annotations

from typing import Any


def queue_item_message_metadata(item: Any, *, default_source: str = "system") -> dict[str, Any]:
    metadata = dict(getattr(item, "metadata", None) or {})
    source = getattr(item, "source", None) or default_source
    is_steer = bool(getattr(item, "is_steer", False) or source == "owner")
    metadata.update(
        {
            "source": source,
            "notification_type": getattr(item, "notification_type", None),
            "sender_name": getattr(item, "sender_name", None),
            "sender_avatar_url": getattr(item, "sender_avatar_url", None),
            "sender_id": getattr(item, "sender_id", None),
            "is_steer": is_steer,
        }
    )
    return metadata
