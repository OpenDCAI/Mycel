"""Runtime scheduler for thread-bound scheduled tasks."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Iterable
from datetime import datetime
from typing import Any, Awaitable, Callable

from croniter import croniter

from backend.scheduled_tasks import service

DispatchFn = Callable[[str, str], Awaitable[dict[str, Any]]]

_CHECK_INTERVAL_SEC = 60

logger = logging.getLogger(__name__)


def _compute_next_trigger_at(cron_expression: str, base_ms: int) -> int:
    base = datetime.fromtimestamp(base_ms / 1000)
    return int(croniter(cron_expression, base).get_next(datetime).timestamp() * 1000)


def _resolve_run_status(dispatch_result: dict[str, Any]) -> str:
    if dispatch_result.get("status") == "injected" or dispatch_result.get("routing") == "steer":
        return "queued"
    return "dispatched"


def mark_run_completed(scheduled_task_run_id: str) -> dict[str, Any] | None:
    return service.update_scheduled_task_run(
        scheduled_task_run_id,
        status="completed",
        completed_at=int(time.time() * 1000),
    )


def mark_run_failed(scheduled_task_run_id: str, error: str) -> dict[str, Any] | None:
    return service.update_scheduled_task_run(
        scheduled_task_run_id,
        status="failed",
        completed_at=int(time.time() * 1000),
        error=error,
    )


def mark_run_dispatched(
    scheduled_task_run_id: str,
    *,
    thread_run_id: str = "",
    routing: str = "direct",
) -> dict[str, Any] | None:
    dispatch_result: dict[str, Any] = {"status": "started", "routing": routing}
    if thread_run_id:
        dispatch_result["run_id"] = thread_run_id
    return service.update_scheduled_task_run(
        scheduled_task_run_id,
        status="dispatched",
        started_at=int(time.time() * 1000),
        thread_run_id=thread_run_id,
        dispatch_result=dispatch_result,
    )


def collect_scheduled_task_run_ids(message_metadata: dict[str, Any] | None) -> list[str]:
    if not message_metadata:
        return []
    run_ids: list[str] = []
    single = message_metadata.get("scheduled_task_run_id")
    if single:
        run_ids.append(str(single))
    multiple = message_metadata.get("scheduled_task_run_ids")
    if isinstance(multiple, (list, tuple, set)):
        run_ids.extend(str(item) for item in multiple if item)
    return list(dict.fromkeys(run_ids))


def finalize_scheduled_task_run_ids(run_ids: Iterable[str], error: str | None = None) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for run_id in dict.fromkeys(str(item) for item in run_ids if item):
        result = mark_run_failed(run_id, error) if error else mark_run_completed(run_id)
        if result is not None:
            results.append(result)
    return results


def finalize_from_message_metadata(message_metadata: dict[str, Any] | None, error: str | None = None) -> dict[str, Any] | None:
    run_ids = collect_scheduled_task_run_ids(message_metadata)
    if not run_ids:
        return None
    results = finalize_scheduled_task_run_ids(run_ids, error=error)
    return results[-1] if results else None


class ScheduledTaskScheduler:
    def __init__(
        self,
        app: Any | None = None,
        dispatch_fn: DispatchFn | None = None,
        check_interval_sec: int = _CHECK_INTERVAL_SEC,
    ) -> None:
        self._app = app
        self._dispatch_fn = dispatch_fn
        self._check_interval_sec = check_interval_sec
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        try:
            await self.check_due_tasks()
        except Exception:
            logger.exception("[scheduled-task-scheduler] initial due check failed")
        self._task = asyncio.create_task(self._scheduler_loop())

    async def stop(self) -> None:
        self._running = False
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    def is_due(self, scheduled_task: dict[str, Any]) -> bool:
        if not scheduled_task.get("enabled"):
            return False
        cron_expression = scheduled_task.get("cron_expression", "")
        last_triggered_at = int(scheduled_task.get("last_triggered_at", 0) or 0)
        now = datetime.now()
        prev_fire_ms = int(croniter(cron_expression, now).get_prev(datetime).timestamp() * 1000)
        return last_triggered_at < prev_fire_ms

    async def trigger_task(self, scheduled_task_id: str) -> dict[str, Any]:
        scheduled_task = service.get_scheduled_task(scheduled_task_id)
        if scheduled_task is None:
            raise ValueError(f"Scheduled task not found: {scheduled_task_id}")

        run = service.create_scheduled_task_run(
            scheduled_task_id=scheduled_task["id"],
            thread_id=scheduled_task["thread_id"],
            status="queued",
        )
        started_at = int(time.time() * 1000)
        try:
            dispatch_result = await self._dispatch(scheduled_task["thread_id"], scheduled_task["instruction"], run["id"])
        except Exception as exc:
            return service.update_scheduled_task_run(
                run["id"],
                status="failed",
                started_at=started_at,
                completed_at=int(time.time() * 1000),
                error=str(exc),
            )

        thread_run_id = str(dispatch_result.get("run_id", "") or "")
        now_ms = int(time.time() * 1000)
        service.update_scheduled_task(
            scheduled_task["id"],
            last_triggered_at=now_ms,
            next_trigger_at=_compute_next_trigger_at(scheduled_task["cron_expression"], now_ms),
        )
        return service.update_scheduled_task_run(
            run["id"],
            status=_resolve_run_status(dispatch_result),
            started_at=started_at,
            dispatch_result=dispatch_result,
            thread_run_id=thread_run_id,
        )

    async def check_due_tasks(self) -> list[dict[str, Any]]:
        triggered: list[dict[str, Any]] = []
        for scheduled_task in service.list_scheduled_tasks():
            if self.is_due(scheduled_task):
                triggered.append(await self.trigger_task(scheduled_task["id"]))
        return triggered

    async def _scheduler_loop(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(self._check_interval_sec)
                if not self._running:
                    break
                await self.check_due_tasks()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("[scheduled-task-scheduler] loop error")

    async def _dispatch(self, thread_id: str, instruction: str, scheduled_task_run_id: str | None = None) -> dict[str, Any]:
        if self._dispatch_fn is not None:
            return await self._dispatch_fn(thread_id, instruction)
        if self._app is None:
            raise RuntimeError("No dispatch function or app configured")
        from backend.web.services.message_routing import route_message_to_brain

        return await route_message_to_brain(
            self._app,
            thread_id,
            instruction,
            source="scheduled_task",
            extra_metadata={"scheduled_task_run_id": scheduled_task_run_id} if scheduled_task_run_id else None,
        )
