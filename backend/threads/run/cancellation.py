"""Cancellation and terminal follow-up helpers for thread runtime runs."""

import asyncio
import json
from typing import Any

from core.runtime.notifications import is_terminal_background_notification


def _is_terminal_background_notification_message(
    message: str,
    *,
    source: str | None,
    notification_type: str | None,
) -> bool:
    return is_terminal_background_notification(
        message,
        source=source,
        notification_type=notification_type,
    )


def partition_terminal_followups(items: list[Any]) -> tuple[list[Any], list[Any]]:
    terminal = []
    passthrough = []
    for item in items:
        if _is_terminal_background_notification_message(
            item.content,
            source=item.source or "system",
            notification_type=item.notification_type,
        ):
            terminal.append(item)
        else:
            passthrough.append(item)
    return terminal, passthrough


def _message_metadata_dict(message_metadata: dict[str, Any] | None) -> dict[str, Any]:
    return dict(message_metadata or {})


def _message_already_persisted(message: Any, *, content: str, metadata: dict[str, Any]) -> bool:
    if message.__class__.__name__ != "HumanMessage":
        return False
    if getattr(message, "content", None) != content:
        return False
    return (getattr(message, "metadata", None) or {}) == metadata


async def persist_cancelled_run_input_if_missing(
    *,
    agent: Any,
    config: dict[str, Any],
    message: str,
    message_metadata: dict[str, Any] | None,
) -> None:
    graph = getattr(agent, "agent", None)
    if graph is None or not hasattr(graph, "aget_state") or not hasattr(graph, "aupdate_state"):
        return

    from langchain_core.messages import HumanMessage

    metadata = _message_metadata_dict(message_metadata)
    state = await graph.aget_state(config)
    persisted = list((getattr(state, "values", None) or {}).get("messages", []))
    if persisted and _message_already_persisted(persisted[-1], content=message, metadata=metadata):
        return

    # @@@cancelled-run-input-persist - a started run has already accepted this
    # input at the caller boundary. If cancellation lands before the next loop
    # checkpoint save, persist the input here so later turns do not pretend it
    # never happened.
    candidate = HumanMessage(content=message, metadata=metadata) if metadata else HumanMessage(content=message)
    await graph.aupdate_state(config, {"messages": [candidate]})


def _is_owner_steer_followup_message(
    *,
    source: str | None,
    notification_type: str | None,
) -> bool:
    return source == "owner" and notification_type == "steer"


async def persist_cancelled_owner_steers(
    *,
    agent: Any,
    config: dict[str, Any],
    items: list[dict[str, str | None]],
) -> None:
    graph = getattr(agent, "agent", None)
    if graph is None or not hasattr(graph, "aupdate_state") or not items:
        return

    from langchain_core.messages import HumanMessage

    # @@@cancelled-steer-persist - accepted steer is a real user turn. If the
    # active run is cancelled before the next model call, we must checkpoint it
    # now instead of letting it silently relaunch as a ghost instruction.
    await graph.aupdate_state(
        config,
        {
            "messages": [
                HumanMessage(
                    content=str(item["content"] or ""),
                    metadata={
                        "source": "owner",
                        "notification_type": "steer",
                        "is_steer": True,
                    },
                )
                for item in items
            ]
        },
    )


async def flush_cancelled_owner_steers(
    *,
    agent: Any,
    config: dict[str, Any],
    thread_id: str,
    app: Any,
) -> None:
    qm = app.state.queue_manager
    queued_items = qm.drain_all(thread_id)
    if not queued_items:
        return

    owner_steers: list[dict[str, str | None]] = []
    passthrough: list[Any] = []
    for item in queued_items:
        if _is_owner_steer_followup_message(
            source=item.source,
            notification_type=item.notification_type,
        ):
            owner_steers.append(
                {
                    "content": item.content,
                    "source": item.source or "owner",
                    "notification_type": item.notification_type,
                }
            )
        else:
            passthrough.append(item)

    await persist_cancelled_owner_steers(agent=agent, config=config, items=owner_steers)

    for item in passthrough:
        qm.enqueue(
            item.content,
            thread_id,
            notification_type=item.notification_type,
            source=item.source,
            sender_id=item.sender_id,
            sender_name=item.sender_name,
            sender_avatar_url=item.sender_avatar_url,
            is_steer=item.is_steer,
        )


async def emit_queued_terminal_followups(
    *,
    app: Any,
    thread_id: str,
    emit: Any,
) -> list[dict[str, str | None]]:
    emitted_terminal: list[dict[str, str | None]] = []

    async def _drain_once() -> bool:
        queued_items = app.state.queue_manager.drain_all(thread_id)
        extra_terminal, passthrough = partition_terminal_followups(queued_items)
        for item in passthrough:
            app.state.queue_manager.enqueue(
                item.content,
                thread_id,
                notification_type=item.notification_type,
                source=item.source,
                sender_id=item.sender_id,
                sender_name=item.sender_name,
                sender_avatar_url=item.sender_avatar_url,
                is_steer=item.is_steer,
            )
        for item in extra_terminal:
            await emit(
                {
                    "event": "notice",
                    "data": json.dumps(
                        {
                            "content": item.content,
                            "source": item.source or "system",
                            "notification_type": item.notification_type,
                        },
                        ensure_ascii=False,
                    ),
                }
            )
            emitted_terminal.append(
                {
                    "content": item.content,
                    "source": item.source or "system",
                    "notification_type": item.notification_type,
                }
            )
        return bool(extra_terminal)

    # @@@terminal-followup-race-window - multiple background tasks can finish
    # while the first notice-only followthrough run is being emitted. Drain once
    # for already-persisted notices, yield one loop tick, then drain again so
    # same-turn terminal completions are folded into the same stable followthrough.
    await _drain_once()
    await asyncio.sleep(0)
    await _drain_once()
    return emitted_terminal
