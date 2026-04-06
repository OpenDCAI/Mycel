"""CronService — background scheduler that triggers task creation from cron jobs.

Uses a simple asyncio background loop + croniter for cron expression parsing.
Checks the cron_jobs table every 60 seconds and triggers due jobs.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Any

from croniter import croniter

from backend.web.services import cron_job_service, task_service

logger = logging.getLogger(__name__)

_CHECK_INTERVAL_SEC = 60
_ALLOWED_TEMPLATE_KEYS = {"title", "description", "priority", "assignee_id", "deadline", "tags"}


class CronService:
    """Background cron scheduler that creates panel_tasks from cron job templates."""

    def __init__(self) -> None:
        self._running = False
        self._task: asyncio.Task | None = None

    # -- public API ----------------------------------------------------------

    async def start(self) -> None:
        """Start the background scheduler loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._scheduler_loop())
        logger.info("[cron-service] started")

    async def stop(self) -> None:
        """Gracefully stop the scheduler."""
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("[cron-service] stopped")

    async def trigger_job(self, job_id: str, owner_user_id: str | None = None) -> dict[str, Any] | None:
        """Manually trigger a cron job. Creates a task from template.

        Returns the created task dict, or None if the job doesn't exist,
        is disabled, or has an invalid template.
        """
        job = await asyncio.to_thread(cron_job_service.get_cron_job, job_id, owner_user_id=owner_user_id)
        if job is None:
            return None
        if not job.get("enabled"):
            return None

        # Parse task template
        template_str = job.get("task_template", "{}")
        try:
            template = json.loads(template_str)
        except (json.JSONDecodeError, TypeError):
            logger.warning("[cron-service] job %s has invalid JSON template", job_id)
            return None

        # Build task fields from template — only allow known safe keys
        task_fields: dict[str, Any] = {k: v for k, v in template.items() if k in _ALLOWED_TEMPLATE_KEYS}
        task_fields["source"] = "cron"
        task_fields["cron_job_id"] = job_id
        task_fields["owner_user_id"] = job.get("owner_user_id")

        task = await asyncio.to_thread(task_service.create_task, **task_fields)

        # Update last_run_at on the cron job
        now_ms = int(time.time() * 1000)
        await asyncio.to_thread(
            cron_job_service.update_cron_job,
            job_id,
            owner_user_id=job.get("owner_user_id"),
            last_run_at=now_ms,
        )

        logger.info("[cron-service] triggered job %s → task %s", job_id, task.get("id"))
        return task

    def is_due(self, job: dict[str, Any]) -> bool:
        """Check if a cron job is due for execution.

        Uses croniter to determine the last expected fire time. If the job
        hasn't run since that time, it is due.
        """
        if not job.get("enabled"):
            return False

        cron_expr = job.get("cron_expression", "")
        last_run_ms = job.get("last_run_at", 0)
        now = datetime.now()

        try:
            cron = croniter(cron_expr, now)
        except (ValueError, KeyError):
            logger.warning("[cron-service] invalid cron expression: %s", cron_expr)
            return False

        # Get the previous fire time relative to now
        prev_fire = cron.get_prev(datetime)
        prev_fire_ms = int(prev_fire.timestamp() * 1000)

        # The job is due if it hasn't run since the last scheduled fire time
        return last_run_ms < prev_fire_ms

    # -- internal ------------------------------------------------------------

    async def _scheduler_loop(self) -> None:
        """Background loop: check every 60s for due cron jobs."""
        while self._running:
            try:
                await asyncio.sleep(_CHECK_INTERVAL_SEC)
                if not self._running:
                    break
                await self._check_and_trigger()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("[cron-service] error in scheduler loop")

    async def _check_and_trigger(self) -> None:
        """Check all enabled cron jobs and trigger those that are due."""
        jobs = await asyncio.to_thread(cron_job_service.list_cron_jobs)
        for job in jobs:
            if self.is_due(job):
                try:
                    await self.trigger_job(job["id"])
                except Exception:
                    logger.exception("[cron-service] failed to trigger job %s — skipping", job["id"])
