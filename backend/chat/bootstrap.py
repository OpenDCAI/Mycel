"""Chat runtime bootstrap owned by the chat backend."""

from __future__ import annotations

from typing import Any

from backend.identity.avatar.urls import avatar_url
from backend.threads.chat_adapters.chat_inlet import make_chat_delivery_fn
from messaging.delivery.resolver import HireVisitDeliveryResolver
from messaging.realtime.events import ChatEventBus
from messaging.realtime.typing import TypingTracker
from messaging.relationships.service import RelationshipService
from messaging.service import MessagingService


def attach_chat_runtime(app: Any, storage_container: Any) -> None:
    user_repo = getattr(app.state, "user_repo", None)
    thread_repo = getattr(app.state, "thread_repo", None)
    if user_repo is None or thread_repo is None:
        raise RuntimeError("attach_chat_runtime requires user_repo and thread_repo on app.state")

    app.state.chat_repo = storage_container.chat_repo()
    app.state.contact_repo = storage_container.contact_repo()
    app.state.chat_member_repo = storage_container.chat_member_repo()
    app.state.messages_repo = storage_container.messages_repo()
    app.state.relationship_repo = storage_container.relationship_repo()

    app.state.chat_event_bus = ChatEventBus()
    app.state.typing_tracker = TypingTracker(app.state.chat_event_bus)
    app.state.relationship_service = RelationshipService(app.state.relationship_repo)

    delivery_resolver = HireVisitDeliveryResolver(
        contact_repo=app.state.contact_repo,
        chat_member_repo=app.state.chat_member_repo,
        relationship_repo=app.state.relationship_repo,
    )

    app.state.messaging_service = MessagingService(
        chat_repo=app.state.chat_repo,
        chat_member_repo=app.state.chat_member_repo,
        messages_repo=app.state.messages_repo,
        user_repo=user_repo,
        thread_repo=thread_repo,
        event_bus=app.state.chat_event_bus,
        delivery_resolver=delivery_resolver,
        avatar_url_builder=avatar_url,
    )


def wire_chat_delivery(app: Any) -> None:
    app.state.messaging_service.set_delivery_fn(make_chat_delivery_fn(app))
