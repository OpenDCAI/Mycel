from __future__ import annotations

import json
import time
from collections.abc import Awaitable, Callable
from typing import Any

from backend.threads.message_content import strip_system_tags


async def emit_run_prologue(
    *,
    agent: Any,
    thread_id: str,
    message: str,
    message_metadata: dict[str, Any] | None,
    run_id: str,
    app: Any,
    emit: Callable[[dict[str, str]], Awaitable[None]],
) -> tuple[str | None, str | None]:
    meta = message_metadata or {}
    src = meta.get("source")

    # @@@run-source-tracking — set on runtime for source tracking
    if hasattr(agent, "runtime"):
        agent.runtime.current_run_source = src or "owner"

    app.state.thread_last_active[thread_id] = time.time()

    # @@@user-entry — emit user_message so display_builder can add a UserMessage
    # entry. Skip for steers — wake_handler already emitted user_message at
    # enqueue time (@@@steer-instant-feedback). Note: is_steer is not persisted
    # in queue, so check notification_type too.
    is_steer = meta.get("is_steer") or meta.get("notification_type") == "steer"
    if meta.get("ask_user_question_answered"):
        await emit(
            {
                "event": "user_message",
                "data": json.dumps(
                    {
                        "content": "",
                        "showing": False,
                        "ask_user_question_answered": meta["ask_user_question_answered"],
                    },
                    ensure_ascii=False,
                ),
            }
        )
    elif (not src or src == "owner") and not is_steer:
        # @@@strip-for-display — agent sees full content (with system-reminder),
        # frontend sees clean text (tags stripped)
        display_content = strip_system_tags(message) if "<system-reminder>" in message else message
        await emit(
            {
                "event": "user_message",
                "data": json.dumps(
                    {
                        "content": display_content,
                        "showing": True,
                        **({"attachments": meta["attachments"]} if meta.get("attachments") else {}),
                    },
                    ensure_ascii=False,
                ),
            }
        )

    await emit(
        {
            "event": "run_start",
            "data": json.dumps(
                {
                    "thread_id": thread_id,
                    "run_id": run_id,
                    "source": src,
                    "sender_name": meta.get("sender_name"),
                    "showing": True,
                }
            ),
        }
    )

    # @@@run-notice — emit notice right after run_start so frontend folds it
    # into the (re)opened turn. Mirror the cold-path DisplayBuilder rule:
    # any source=system message is a notice; external notices stay chat-only.
    ntype = meta.get("notification_type")
    if src == "system" or (src == "external" and ntype == "chat"):
        await emit(
            {
                "event": "notice",
                "data": json.dumps(
                    {
                        "content": message,
                        "source": src,
                        "notification_type": ntype,
                    },
                    ensure_ascii=False,
                ),
            }
        )

    return src, ntype
