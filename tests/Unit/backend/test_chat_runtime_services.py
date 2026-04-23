import asyncio
from types import SimpleNamespace

from backend.threads.chat_adapters.chat_runtime_services import AppAgentChatRuntimeServices


def test_chat_runtime_services_use_injected_typing_tracker_and_queue_manager():
    started: list[tuple[str, str, str]] = []
    enqueued: list[tuple[str, str, str | None, str | None]] = []

    injected_typing_tracker = SimpleNamespace(start_chat=lambda thread_id, chat_id, user_id: started.append((thread_id, chat_id, user_id)))
    injected_queue_manager = SimpleNamespace(
        enqueue=lambda content, thread_id, notification_type, **meta: enqueued.append(
            (content, thread_id, meta.get("sender_id"), meta.get("sender_name"))
        )
    )

    app = SimpleNamespace(
        state=SimpleNamespace(
            typing_tracker=SimpleNamespace(
                start_chat=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("should use injected tracker"))
            ),
            queue_manager=SimpleNamespace(
                enqueue=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("should use injected queue manager"))
            ),
        )
    )

    services = AppAgentChatRuntimeServices(
        app,
        typing_tracker=injected_typing_tracker,
        thread_repo=SimpleNamespace(get_canonical_thread_for_agent_actor=lambda _user_id: {"id": "thread-1"}),
        queue_manager=injected_queue_manager,
        get_or_create_agent=lambda *_args, **_kwargs: None,
        resolve_thread_sandbox=lambda *_args, **_kwargs: "local",
        ensure_thread_handlers=lambda *_args, **_kwargs: None,
    )

    services.start_chat("thread-1", "chat-1", "agent-user-1")
    services.enqueue_chat_message(
        content="hello",
        thread_id="thread-1",
        sender_id="human-user-1",
        sender_name="Human",
        sender_avatar_url=None,
    )

    assert started == [("thread-1", "chat-1", "agent-user-1")]
    assert enqueued == [("hello", "thread-1", "human-user-1", "Human")]


def test_chat_runtime_services_use_injected_runtime_callables():
    calls: list[tuple[str, object]] = []
    agent = object()

    async def _get_or_create_agent(app, sandbox_type: str, *, thread_id: str):
        calls.append(("get_or_create_agent", (app, sandbox_type, thread_id)))
        return agent

    def _resolve_thread_sandbox(app, thread_id: str):
        calls.append(("resolve_thread_sandbox", (app, thread_id)))
        return "local"

    def _ensure_thread_handlers(target_agent, thread_id: str, app):
        calls.append(("ensure_thread_handlers", (target_agent, thread_id, app)))

    app = SimpleNamespace(state=SimpleNamespace())
    services = AppAgentChatRuntimeServices(
        app,
        typing_tracker=SimpleNamespace(start_chat=lambda *_args, **_kwargs: None),
        thread_repo=SimpleNamespace(get_canonical_thread_for_agent_actor=lambda _user_id: {"id": "thread-1"}),
        queue_manager=SimpleNamespace(enqueue=lambda *_args, **_kwargs: None),
        get_or_create_agent=_get_or_create_agent,
        resolve_thread_sandbox=_resolve_thread_sandbox,
        ensure_thread_handlers=_ensure_thread_handlers,
    )

    result = asyncio.run(services.get_or_create_thread_agent("thread-1"))

    assert result is agent
    assert calls == [
        ("resolve_thread_sandbox", (app, "thread-1")),
        ("get_or_create_agent", (app, "local", "thread-1")),
        ("ensure_thread_handlers", (agent, "thread-1", app)),
    ]
