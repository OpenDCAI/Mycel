from types import SimpleNamespace

from backend.chat import bootstrap as chat_bootstrap


def test_attach_chat_runtime_wires_chat_state(monkeypatch):
    chat_repo = object()
    contact_repo = object()
    chat_member_repo = object()
    messages_repo = object()
    relationship_repo = object()
    chat_join_request_repo = object()

    storage_container = SimpleNamespace(
        chat_repo=lambda: chat_repo,
        contact_repo=lambda: contact_repo,
        chat_member_repo=lambda: chat_member_repo,
        messages_repo=lambda: messages_repo,
        relationship_repo=lambda: relationship_repo,
        chat_join_request_repo=lambda: chat_join_request_repo,
    )

    class _EventBus:
        pass

    class _TypingTracker:
        def __init__(self, event_bus):
            self.event_bus = event_bus

    class _RelationshipService:
        def __init__(self, repo):
            self.repo = repo

    class _MessagingService:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.delivery_fn = None

        def set_delivery_fn(self, delivery_fn):
            self.delivery_fn = delivery_fn

    class _ChatJoinRequestService:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    event_bus = _EventBus()

    monkeypatch.setattr(chat_bootstrap, "ChatEventBus", lambda: event_bus)
    monkeypatch.setattr(chat_bootstrap, "TypingTracker", _TypingTracker)
    monkeypatch.setattr(chat_bootstrap, "RelationshipService", _RelationshipService)
    monkeypatch.setattr(chat_bootstrap, "HireVisitDeliveryResolver", lambda **kwargs: kwargs)
    monkeypatch.setattr(chat_bootstrap, "MessagingService", _MessagingService)
    monkeypatch.setattr(chat_bootstrap, "ChatJoinRequestService", _ChatJoinRequestService)
    app = SimpleNamespace(
        state=SimpleNamespace(
            user_repo=object(),
            thread_repo=object(),
        )
    )

    state = chat_bootstrap.attach_chat_runtime(
        app,
        storage_container,
        user_repo=app.state.user_repo,
        thread_repo=app.state.thread_repo,
    )

    assert app.state.chat_runtime_state is state
    assert state.chat_repo is chat_repo
    assert state.chat_event_bus is event_bus
    assert state.contact_repo is contact_repo
    assert state.typing_tracker.event_bus is event_bus
    assert state.relationship_service.repo is relationship_repo
    assert state.chat_join_request_service.kwargs["chat_join_request_repo"] is chat_join_request_repo
    assert state.chat_join_request_service.kwargs["chat_repo"] is chat_repo
    assert state.chat_join_request_service.kwargs["chat_member_repo"] is chat_member_repo
    assert state.chat_join_request_service.kwargs["messaging_service"] is state.messaging_service
    assert state.messaging_service.kwargs["chat_repo"] is chat_repo
    assert state.messaging_service.kwargs["delivery_resolver"]["contact_repo"] is contact_repo
    assert state.messaging_service.kwargs["thread_repo"] is app.state.thread_repo
    assert state.messaging_service.delivery_fn is None


def test_attach_chat_runtime_requires_explicit_user_repo_and_thread_repo():
    app = SimpleNamespace(state=SimpleNamespace(user_repo=object(), thread_repo=object()))
    storage_container = SimpleNamespace(
        chat_repo=lambda: object(),
        contact_repo=lambda: object(),
        chat_member_repo=lambda: object(),
        messages_repo=lambda: object(),
        relationship_repo=lambda: object(),
        chat_join_request_repo=lambda: object(),
    )

    try:
        chat_bootstrap.attach_chat_runtime(app, storage_container)
    except TypeError as exc:
        message = str(exc)
        assert "user_repo" in message
        assert "thread_repo" in message
    else:
        raise AssertionError("attach_chat_runtime should require explicit user_repo/thread_repo kwargs")


def test_wire_chat_delivery_binds_delivery_fn(monkeypatch):
    delivery_fn = object()
    messaging_service = SimpleNamespace(delivery_fn=None)
    activity_reader = object()
    thread_repo = object()

    def _set_delivery_fn(value):
        messaging_service.delivery_fn = value

    messaging_service.set_delivery_fn = _set_delivery_fn

    app = SimpleNamespace(state=SimpleNamespace())

    monkeypatch.setattr(
        chat_bootstrap,
        "make_chat_delivery_fn",
        lambda target_app, *, activity_reader, thread_repo: delivery_fn,
    )

    chat_bootstrap.wire_chat_delivery(
        app,
        messaging_service=messaging_service,
        activity_reader=activity_reader,
        thread_repo=thread_repo,
    )

    assert messaging_service.delivery_fn is delivery_fn


def test_wire_relationship_request_notifications_binds_notification_fn(monkeypatch):
    notification_fn = object()
    relationship_service = SimpleNamespace(notification_fn=None)
    activity_reader = object()
    thread_repo = object()
    user_repo = object()

    def _set_notification_fn(value):
        relationship_service.notification_fn = value

    relationship_service.set_relationship_request_notification_fn = _set_notification_fn

    app = SimpleNamespace(state=SimpleNamespace())

    monkeypatch.setattr(
        chat_bootstrap,
        "make_relationship_request_notification_fn",
        lambda target_app, *, activity_reader, thread_repo, user_repo: notification_fn,
    )

    chat_bootstrap.wire_relationship_request_notifications(
        app,
        relationship_service=relationship_service,
        activity_reader=activity_reader,
        thread_repo=thread_repo,
        user_repo=user_repo,
    )

    assert relationship_service.notification_fn is notification_fn
