from __future__ import annotations

from typing import Any

from sandbox.manager import lookup_sandbox_for_thread


def resolve_thread_sandbox(app_obj: Any, thread_id: str) -> str:
    mapping = app_obj.state.thread_sandbox
    if thread_id in mapping:
        return mapping[thread_id]
    thread_data = app_obj.state.thread_repo.get_by_id(thread_id) if hasattr(app_obj.state, "thread_repo") else None
    if thread_data:
        mapping[thread_id] = thread_data.get("sandbox_type", "local")
        if thread_data.get("cwd"):
            app_obj.state.thread_cwd.setdefault(thread_id, thread_data["cwd"])
        return thread_data.get("sandbox_type", "local")
    detected = lookup_sandbox_for_thread(thread_id)
    if detected:
        mapping[thread_id] = detected
        return detected
    return "local"
