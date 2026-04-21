"""Chat runtime bootstrap owned by the chat backend."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.identity.avatar.urls import avatar_url
from backend.threads.chat_adapters.chat_inlet import make_chat_delivery_fn
from messaging.delivery.resolver import HireVisitDeliveryResolver
from messaging.realtime.events import ChatEventBus
from messaging.realtime.typing import TypingTracker
from messaging.relationships.service import RelationshipService
from messaging.service import MessagingService


@dataclass(frozen=True)
class ChatRuntimeState:
    contact_repo: Any
    typing_tracker: Any
    relationship_service: Any
    messaging_service: Any


def attach_chat_runtime(
    app: Any,
    storage_container: Any,
    *,
    user_repo: Any,
    thread_repo: Any,
) -> ChatRuntimeState:
    chat_repo = storage_container.chat_repo()
    contact_repo = storage_container.contact_repo()
    chat_member_repo = storage_container.chat_member_repo()
    messages_repo = storage_container.messages_repo()
    relationship_repo = storage_container.relationship_repo()
    chat_event_bus = ChatEventBus()
    typing_tracker = TypingTracker(chat_event_bus)
    relationship_service = RelationshipService(relationship_repo)

    delivery_resolver = HireVisitDeliveryResolver(
        contact_repo=contact_repo,
        chat_member_repo=chat_member_repo,
        relationship_repo=relationship_repo,
    )

    messaging_service = MessagingService(
        chat_repo=chat_repo,
        chat_member_repo=chat_member_repo,
        messages_repo=messages_repo,
        user_repo=user_repo,
        thread_repo=thread_repo,
        event_bus=chat_event_bus,
        delivery_resolver=delivery_resolver,
        avatar_url_builder=avatar_url,
    )

    app.state.chat_repo = chat_repo
    app.state.contact_repo = contact_repo
    app.state.chat_member_repo = chat_member_repo
    app.state.messages_repo = messages_repo
    app.state.relationship_repo = relationship_repo
    app.state.chat_event_bus = chat_event_bus
    app.state.typing_tracker = typing_tracker
    app.state.relationship_service = relationship_service
    app.state.messaging_service = messaging_service
    # @@@chat-bootstrap-borrowable-state - bootstrap still attaches chat-owned
    # state onto app.state for the wider app, but it also returns the freshly
    # built runtime objects so enclosing lifespans do not need to reread them.
    state = ChatRuntimeState(
        contact_repo=contact_repo,
        typing_tracker=typing_tracker,
        relationship_service=relationship_service,
        messaging_service=messaging_service,
    )
    app.state.chat_runtime_state = state
    return state


def wire_chat_delivery(app: Any, *, messaging_service: Any, activity_reader: Any, thread_repo: Any) -> None:
    # @@@chat-delivery-borrowed-service - delivery wiring runs after chat bootstrap,
    # but it should still consume the already-constructed messaging service
    # explicitly rather than re-reading app.state and silently depending on
    # bootstrap ordering through a hidden state lookup.
    messaging_service.set_delivery_fn(
        make_chat_delivery_fn(
            app,
            activity_reader=activity_reader,
            thread_repo=thread_repo,
        )
    )
