from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.identity.avatar.urls import avatar_url
from backend.threads.chat_adapters.chat_inlet import make_chat_delivery_fn
from backend.threads.chat_adapters.chat_join_inlet import make_chat_join_rejection_notification_fn
from backend.threads.chat_adapters.relationship_inlet import make_relationship_request_notification_fn
from messaging.delivery.resolver import HireVisitDeliveryResolver
from messaging.join_requests import ChatJoinRequestService
from messaging.realtime.events import ChatEventBus
from messaging.realtime.typing import TypingTracker
from messaging.relationships.service import RelationshipService
from messaging.service import MessagingService


@dataclass(frozen=True)
class ChatRuntimeState:
    chat_repo: Any
    chat_event_bus: Any
    contact_repo: Any
    typing_tracker: Any
    relationship_service: Any
    chat_join_request_service: Any
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
    chat_join_request_repo = storage_container.chat_join_request_repo()
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
        contact_repo=contact_repo,
        relationship_service=relationship_service,
        event_bus=chat_event_bus,
        delivery_resolver=delivery_resolver,
        avatar_url_builder=avatar_url,
    )
    chat_join_request_service = ChatJoinRequestService(
        chat_repo=chat_repo,
        chat_member_repo=chat_member_repo,
        chat_join_request_repo=chat_join_request_repo,
        messaging_service=messaging_service,
    )

    # @@@chat-bootstrap-borrowable-state - chat bootstrap now keeps its owned
    # runtime objects inside the returned chat_runtime_state so the app
    # has one canonical read surface instead of loose top-level mirrors.
    state = ChatRuntimeState(
        chat_repo=chat_repo,
        chat_event_bus=chat_event_bus,
        contact_repo=contact_repo,
        typing_tracker=typing_tracker,
        relationship_service=relationship_service,
        chat_join_request_service=chat_join_request_service,
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


def wire_relationship_request_notifications(
    app: Any,
    *,
    relationship_service: Any,
    activity_reader: Any,
    thread_repo: Any,
    user_repo: Any,
) -> None:
    relationship_service.set_relationship_request_notification_fn(
        make_relationship_request_notification_fn(
            app,
            activity_reader=activity_reader,
            thread_repo=thread_repo,
            user_repo=user_repo,
        )
    )


def wire_chat_join_request_notifications(
    app: Any,
    *,
    chat_join_request_service: Any,
    activity_reader: Any,
    thread_repo: Any,
    user_repo: Any,
) -> None:
    chat_join_request_service.set_join_request_rejected_notification_fn(
        make_chat_join_rejection_notification_fn(
            app,
            activity_reader=activity_reader,
            thread_repo=thread_repo,
            user_repo=user_repo,
        )
    )
