"""Compatibility shell for thread runtime idle reaper helpers."""

from typing import Any

from backend.thread_runtime.pool import idle_reaper as _owner
from backend.web.core.config import IDLE_REAPER_INTERVAL_SEC

from .sandbox_service import init_providers_and_managers


def run_idle_reaper_once(app_obj: Any) -> int:
    _owner.init_providers_and_managers = init_providers_and_managers
    return _owner.run_idle_reaper_once(app_obj)


async def idle_reaper_loop(app_obj: Any) -> None:
    _owner.init_providers_and_managers = init_providers_and_managers
    _owner.IDLE_REAPER_INTERVAL_SEC = IDLE_REAPER_INTERVAL_SEC
    await _owner.idle_reaper_loop(app_obj)
