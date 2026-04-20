"""Event emission helpers for thread runtime runs."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from storage.contracts import RunEventRepo

append_event = None


def resolve_run_event_repo(agent: Any) -> RunEventRepo:
    storage_container = getattr(agent, "storage_container", None)
    if storage_container is None:
        raise RuntimeError("streaming_service requires agent.storage_container.run_event_repo()")

    # @@@runtime-storage-consumer - runtime run lifecycle must consume injected storage container, not assignment-only wiring.
    run_event_repo = getattr(storage_container, "run_event_repo", None)
    if not callable(run_event_repo):
        raise RuntimeError("streaming_service requires agent.storage_container.run_event_repo()")
    repo = run_event_repo()
    if not isinstance(repo, RunEventRepo):
        raise RuntimeError("agent.storage_container.run_event_repo() returned an invalid repo")
    return repo


def build_emit(
    *,
    thread_id: str,
    run_id: str,
    thread_buf: Any,
    run_event_repo: RunEventRepo,
    display_builder: Any,
) -> Callable[[dict[str, Any], str | None], Awaitable[None]]:
    async def emit(event: dict[str, Any], message_id: str | None = None) -> None:
        if append_event is None:
            raise RuntimeError("thread_runtime.run.emit requires append_event binding")
        seq = await append_event(
            thread_id,
            run_id,
            event,
            message_id,
            run_event_repo=run_event_repo,
        )
        try:
            data = json.loads(event.get("data", "{}")) if isinstance(event.get("data"), str) else event.get("data", {})
        except (json.JSONDecodeError, TypeError):
            data = event.get("data", {})
        if isinstance(data, dict):
            data["_seq"] = seq
            data["_run_id"] = run_id
            if message_id:
                data["message_id"] = message_id
            event = {**event, "data": json.dumps(data, ensure_ascii=False)}
        await thread_buf.put(event)

        # @@@display-builder — compute display deltas alongside raw events
        event_type = event.get("event", "")
        if event_type and isinstance(data, dict):
            delta = display_builder.apply_event(thread_id, event_type, data)
            if delta:
                # @@@display-delta-source-seq - replay after-filter only knows raw
                # event seqs. Carry the source seq onto the derived delta so a
                # reconnect after GET /thread can skip stale display_delta
                # replays instead of rebuilding the same thread a second time.
                delta["_seq"] = seq
                await thread_buf.put(
                    {
                        "event": "display_delta",
                        "data": json.dumps(delta, ensure_ascii=False),
                    }
                )

    return emit
