"""SSE observer helpers for thread runtime event buffers."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator

from backend.threads.events.buffer import RunEventBuffer, ThreadEventBuffer

type SSEEvent = dict[str, str | int]


async def observe_thread_events(
    thread_buf: ThreadEventBuffer,
    after: int = 0,
) -> AsyncGenerator[SSEEvent, None]:
    """Consume events from a persistent ThreadEventBuffer."""
    async for event in observe_sse_buffer(thread_buf, after=after, stop_on_finish=False):
        yield event


async def observe_run_events(
    buf: RunEventBuffer,
    after: int = 0,
) -> AsyncGenerator[SSEEvent, None]:
    """Consume events from a RunEventBuffer (subagent streams only)."""
    async for event in observe_sse_buffer(buf, after=after, stop_on_finish=True):
        yield event


async def observe_sse_buffer(
    buf: ThreadEventBuffer | RunEventBuffer,
    *,
    after: int,
    stop_on_finish: bool,
) -> AsyncGenerator[SSEEvent, None]:
    """Shared SSE observer loop for thread and run buffers."""
    yield {"retry": 5000}

    cursor = 0
    while True:
        events, cursor = await buf.read_with_timeout(cursor, timeout=30)
        if events is None and not buf.finished.is_set():
            yield {"comment": "keepalive"}
            continue
        if stop_on_finish and not events and buf.finished.is_set():
            break
        if not events:
            continue
        for event in events:
            parsed_data = None
            try:
                parsed_data = json.loads(event.get("data", "{}"))
            except (json.JSONDecodeError, TypeError):
                pass

            if after > 0 and isinstance(parsed_data, dict) and "_seq" in parsed_data and parsed_data["_seq"] <= after:
                continue

            seq_id = str(parsed_data["_seq"]) if isinstance(parsed_data, dict) and "_seq" in parsed_data else None
            if seq_id:
                yield {**event, "id": seq_id}
            else:
                yield event
