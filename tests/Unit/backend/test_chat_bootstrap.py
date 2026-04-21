from types import SimpleNamespace

from backend.chat import bootstrap as chat_bootstrap


def test_chat_bootstrap_uses_identity_avatar_owner() -> None:
    assert chat_bootstrap.avatar_url.__module__ == "backend.identity.avatar.urls"


def test_attach_chat_runtime_wires_chat_state(monkeypatch):
    chat_repo = object()
    contact_repo = object()
    chat_member_repo = object()
    messages_repo = object()
    relationship_repo = object()

    storage_container = SimpleNamespace(
        chat_repo=lambda: chat_repo,
        contact_repo=lambda: contact_repo,
        chat_member_repo=lambda: chat_member_repo,
        messages_repo=lambda: messages_repo,
        relationship_repo=lambda: relationship_repo,
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

    event_bus = _EventBus()

    monkeypatch.setattr(chat_bootstrap, "ChatEventBus", lambda: event_bus)
    monkeypatch.setattr(chat_bootstrap, "TypingTracker", _TypingTracker)
    monkeypatch.setattr(chat_bootstrap, "RelationshipService", _RelationshipService)
    monkeypatch.setattr(chat_bootstrap, "HireVisitDeliveryResolver", lambda **kwargs: kwargs)
    monkeypatch.setattr(chat_bootstrap, "MessagingService", _MessagingService)
    app = SimpleNamespace(
        state=SimpleNamespace(
            user_repo=object(),
            thread_repo=object(),
        )
    )

    chat_bootstrap.attach_chat_runtime(
        app,
        storage_container,
        user_repo=app.state.user_repo,
        thread_repo=app.state.thread_repo,
    )

    assert app.state.chat_repo is chat_repo
    assert app.state.contact_repo is contact_repo
    assert app.state.chat_member_repo is chat_member_repo
    assert app.state.messages_repo is messages_repo
    assert app.state.relationship_repo is relationship_repo
    assert app.state.chat_event_bus is event_bus
    assert app.state.typing_tracker.event_bus is event_bus
    assert app.state.relationship_service.repo is relationship_repo
    assert app.state.messaging_service.kwargs["chat_repo"] is chat_repo
    assert app.state.messaging_service.kwargs["delivery_resolver"]["contact_repo"] is contact_repo
    assert app.state.messaging_service.kwargs["thread_repo"] is app.state.thread_repo
    assert app.state.messaging_service.delivery_fn is None


def test_attach_chat_runtime_requires_explicit_user_repo_and_thread_repo():
    app = SimpleNamespace(state=SimpleNamespace(user_repo=object(), thread_repo=object()))
    storage_container = SimpleNamespace(
        chat_repo=lambda: object(),
        contact_repo=lambda: object(),
        chat_member_repo=lambda: object(),
        messages_repo=lambda: object(),
        relationship_repo=lambda: object(),
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

    app = SimpleNamespace(state=SimpleNamespace(messaging_service=messaging_service))

    monkeypatch.setattr(
        chat_bootstrap,
        "make_chat_delivery_fn",
        lambda target_app, *, activity_reader, thread_repo: delivery_fn,
    )

    chat_bootstrap.wire_chat_delivery(
        app,
        activity_reader=activity_reader,
        thread_repo=thread_repo,
    )

    assert app.state.messaging_service.delivery_fn is delivery_fn
