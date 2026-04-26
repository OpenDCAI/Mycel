"""Pure contracts for Chat delivery wiring."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ChatDeliveryRequest:
    recipient_id: str
    recipient_user: Any
    content: str
    sender_name: str
    sender_type: str
    chat_id: str
    sender_id: str
    sender_avatar_url: str | None
    unread_count: int
    signal: str | None
    wake: bool = True


class ChatDeliveryFn(Protocol):
    def __call__(self, request: ChatDeliveryRequest) -> None: ...
