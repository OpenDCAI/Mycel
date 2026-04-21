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
        queue_manager=injected_queue_manager,
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
