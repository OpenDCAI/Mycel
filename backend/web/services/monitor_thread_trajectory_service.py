"""Monitor thread trajectory read boundary."""

from __future__ import annotations

from typing import Any

from backend.web.services.monitor_trace_service import build_monitor_thread_trajectory


async def load_monitor_thread_trajectory(app: Any, thread_id: str) -> dict[str, Any]:
    return await build_monitor_thread_trajectory(app, thread_id)
