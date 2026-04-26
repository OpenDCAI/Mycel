from core.runtime.middleware.queue.manager import MessageQueueManager


def test_queue_manager_can_enqueue_without_waking(tmp_path) -> None:
    manager = MessageQueueManager(db_path=str(tmp_path / "queue.db"))
    seen: list[str] = []

    manager.register_wake("thread-1", lambda item: seen.append(item.content))
    manager.enqueue("queued only", "thread-1", notification_type="chat", wake=False)

    assert seen == []
    item = manager.dequeue("thread-1")
    assert item is not None
    assert item.content == "queued only"
    assert item.notification_type == "chat"


def test_queue_manager_wakes_by_default(tmp_path) -> None:
    manager = MessageQueueManager(db_path=str(tmp_path / "queue.db"))
    seen: list[str] = []

    manager.register_wake("thread-1", lambda item: seen.append(item.content))
    manager.enqueue("wake now", "thread-1", notification_type="chat")

    assert seen == ["wake now"]
