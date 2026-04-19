from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from backend.thread_runtime.events.buffer import ThreadEventBuffer


class _FakeDisplayBuilder:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, object]]] = []

    def apply_event(self, thread_id: str, event_type: str, data: dict[str, object]) -> dict[str, object] | None:
        self.calls.append((thread_id, event_type, dict(data)))
        if event_type != "text":
            return None
        return {
            "type": "text",
            "content": data["content"],
        }


@pytest.mark.asyncio
async def test_build_emit_carries_seq_run_id_message_id_and_display_delta(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.thread_runtime.run.emit import build_emit

    seq = 40

    async def fake_append_event(thread_id, run_id, event, message_id=None, run_event_repo=None):
        nonlocal seq
        seq += 1
        return seq

    monkeypatch.setattr("backend.thread_runtime.run.emit.append_event", fake_append_event)

    thread_buf = ThreadEventBuffer()
    display_builder = _FakeDisplayBuilder()
    emit = build_emit(
        thread_id="thread-1",
        run_id="run-1",
        thread_buf=thread_buf,
        run_event_repo=SimpleNamespace(),
        display_builder=display_builder,
    )

    await emit(
        {
            "event": "text",
            "data": json.dumps({"content": "hello", "showing": True}, ensure_ascii=False),
        },
        message_id="msg-1",
    )

    events, cursor = await thread_buf.read_with_timeout(0, timeout=0.01)
    assert cursor == 2
    assert events is not None
    assert [event["event"] for event in events] == ["text", "display_delta"]

    raw_payload = json.loads(events[0]["data"])
    assert raw_payload["_seq"] == 41
    assert raw_payload["_run_id"] == "run-1"
    assert raw_payload["message_id"] == "msg-1"

    delta_payload = json.loads(events[1]["data"])
    assert delta_payload == {
        "type": "text",
        "content": "hello",
        "_seq": 41,
    }

    assert display_builder.calls == [
        (
            "thread-1",
            "text",
            {
                "content": "hello",
                "showing": True,
                "_seq": 41,
                "_run_id": "run-1",
                "message_id": "msg-1",
            },
        )
    ]


def test_resolve_run_event_repo_requires_callable_repo_factory() -> None:
    from backend.thread_runtime.run.emit import resolve_run_event_repo

    agent = SimpleNamespace(storage_container=SimpleNamespace(run_event_repo=None))

    with pytest.raises(RuntimeError, match="run_event_repo"):
        resolve_run_event_repo(agent)
