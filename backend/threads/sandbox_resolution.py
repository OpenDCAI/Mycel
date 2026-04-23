"""Shared thread sandbox lookup helpers."""

from __future__ import annotations

from typing import Any

from backend.threads.runtime_access import get_thread_repo
from sandbox.manager import lookup_sandbox_for_thread


def resolve_thread_sandbox(app_obj: Any, thread_id: str) -> str:
    """Look up sandbox type for a thread: memory cache -> repo -> sandbox DB -> default local."""
    mapping = getattr(app_obj.state, "thread_sandbox", None)
    if not isinstance(mapping, dict):
        mapping = {}
        app_obj.state.thread_sandbox = mapping
    if thread_id in mapping:
        return mapping[thread_id]
    thread_data = get_thread_repo(app_obj).get_by_id(thread_id)
    if thread_data:
        mapping[thread_id] = thread_data.get("sandbox_type", "local")
        if thread_data.get("cwd"):
            thread_cwd = getattr(app_obj.state, "thread_cwd", None)
            if not isinstance(thread_cwd, dict):
                thread_cwd = {}
                app_obj.state.thread_cwd = thread_cwd
            thread_cwd.setdefault(thread_id, thread_data["cwd"])
        return thread_data.get("sandbox_type", "local")
    detected = lookup_sandbox_for_thread(thread_id)
    if detected:
        mapping[thread_id] = detected
        return detected
    return "local"
