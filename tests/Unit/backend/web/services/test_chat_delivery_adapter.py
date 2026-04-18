from __future__ import annotations

from backend.web.services import chat_delivery_adapter


def test_delivery_adapter_does_not_export_legacy_private_entries() -> None:
    assert not hasattr(chat_delivery_adapter, "_async_deliver")
    assert not hasattr(chat_delivery_adapter, "_resolve_recipient_thread_id")
