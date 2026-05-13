from __future__ import annotations

from typing import Any

from backend.threads.chat_adapters.runtime_chat_delivery_action import make_runtime_chat_delivery_event_hook


def make_chat_delivery_fn(app: Any, *, activity_reader: Any, thread_repo: Any):
    return make_runtime_chat_delivery_event_hook(
        app,
        thread_repo=thread_repo,
        activity_reader=activity_reader,
    )
