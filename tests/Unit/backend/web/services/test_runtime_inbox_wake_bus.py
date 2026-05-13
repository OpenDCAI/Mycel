from backend.chat.runtime_inbox_wake import PostgresRuntimeInboxWakeBus, RuntimeInboxWakeBus


def test_runtime_inbox_wake_bus_publishes_signal_only() -> None:
    bus = RuntimeInboxWakeBus()
    seen: list[str] = []

    bus.register("external:user-1", lambda: seen.append("woke"))
    bus.publish("external:user-1")

    assert seen == ["woke"]


def test_runtime_inbox_wake_bus_unregister_removes_handler() -> None:
    bus = RuntimeInboxWakeBus()
    seen: list[str] = []

    bus.register("external:user-1", lambda: seen.append("woke"))
    bus.unregister("external:user-1")
    bus.publish("external:user-1")

    assert seen == []


class _RecordingConnection:
    def __init__(self, calls: list[tuple[str, tuple]]) -> None:
        self.calls = calls

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def execute(self, query: str, params: tuple) -> None:
        self.calls.append((query, params))


def test_postgres_runtime_inbox_wake_bus_publishes_local_and_postgres_signal() -> None:
    calls: list[tuple[str, tuple]] = []
    bus = PostgresRuntimeInboxWakeBus(
        "postgres://example",
        connect=lambda _url, autocommit: _RecordingConnection(calls),
    )
    seen: list[str] = []

    bus.register("external:user-1", lambda: seen.append("local"), start_listener=False)
    bus.publish("external:user-1")

    assert seen == ["local"]
    assert calls == [
        (
            "SELECT pg_notify(%s, %s)",
            ("mycel_runtime_inbox_wake", '{"inbox_id":"external:user-1"}'),
        )
    ]


def test_postgres_runtime_inbox_wake_bus_dispatches_remote_payload() -> None:
    bus = PostgresRuntimeInboxWakeBus("postgres://example", connect=lambda *_args, **_kwargs: None)
    seen: list[str] = []

    bus.register("external:user-1", lambda: seen.append("remote"), start_listener=False)
    bus.dispatch_payload('{"inbox_id":"external:user-1"}')

    assert seen == ["remote"]
