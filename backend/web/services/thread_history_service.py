"""Compatibility shell for shared thread history helpers."""

from backend.thread_history import (
    ThreadHistoryTransport,
    build_thread_history_transport,
    get_thread_history_payload,
)

__all__ = [
    "ThreadHistoryTransport",
    "build_thread_history_transport",
    "get_thread_history_payload",
]
