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

    chat_bootstrap.attach_chat_runtime(app, storage_container)

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


def test_wire_chat_delivery_binds_delivery_fn(monkeypatch):
    delivery_fn = object()
    messaging_service = SimpleNamespace(delivery_fn=None)

    def _set_delivery_fn(value):
        messaging_service.delivery_fn = value

    messaging_service.set_delivery_fn = _set_delivery_fn

    app = SimpleNamespace(state=SimpleNamespace(messaging_service=messaging_service))

    monkeypatch.setattr(chat_bootstrap, "make_chat_delivery_fn", lambda target_app: delivery_fn)

    chat_bootstrap.wire_chat_delivery(app)

    assert app.state.messaging_service.delivery_fn is delivery_fn


def test_attach_chat_runtime_gateway_state_wires_runtime_dependencies(monkeypatch):
    queue_repo = object()
    queue_manager = object()
    gateway = object()
    seen: list[tuple[str, object]] = []

    storage_container = SimpleNamespace(queue_repo=lambda: queue_repo)
    app = SimpleNamespace(state=SimpleNamespace())

    monkeypatch.setattr(
        chat_bootstrap,
        "MessageQueueManager",
        lambda *, repo: seen.append(("queue_manager", repo)) or queue_manager,
    )
    monkeypatch.setattr(
        chat_bootstrap,
        "build_agent_runtime_gateway",
        lambda target_app: seen.append(("gateway", target_app)) or gateway,
    )
    monkeypatch.setattr(
        chat_bootstrap,
        "wire_chat_delivery",
        lambda target_app: seen.append(("wire_delivery", target_app)),
    )

    chat_bootstrap.attach_chat_runtime_gateway_state(app, storage_container)

    assert app.state.queue_manager is queue_manager
    assert app.state.agent_pool == {}
    assert app.state.thread_sandbox == {}
    assert app.state.thread_cwd == {}
    assert app.state.thread_tasks == {}
    assert app.state.thread_event_buffers == {}
    assert app.state.subagent_buffers == {}
    assert app.state.thread_last_active == {}
    assert app.state.agent_runtime_gateway is gateway
    assert seen == [
        ("queue_manager", queue_repo),
        ("gateway", app),
        ("wire_delivery", app),
    ]
    assert hasattr(app.state, "thread_locks_guard")
    assert hasattr(app.state, "thread_locks")
