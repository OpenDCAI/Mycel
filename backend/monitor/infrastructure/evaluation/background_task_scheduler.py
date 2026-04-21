"""BackgroundTasks-backed evaluation scheduler."""

from __future__ import annotations

from backend.monitor.infrastructure.evaluation.evaluation_execution_service import run_monitor_evaluation_batch
from backend.monitor.infrastructure.evaluation.evaluation_read_service import make_eval_batch_service
from backend.monitor.infrastructure.evaluation.evaluation_scheduler import EvaluationJobScheduler, EvaluationJobSpec


class BackgroundTaskEvaluationScheduler(EvaluationJobScheduler):
    def __init__(self, schedule_task):
        self._schedule_task = schedule_task

    def submit(self, spec: EvaluationJobSpec) -> None:
        self._schedule_task(
            run_monitor_evaluation_batch,
            batch_id=spec.batch_id,
            scenarios=spec.scenarios,
            base_url=spec.base_url,
            token=spec.token,
            agent_user_id=spec.agent_user_id,
            max_concurrent=spec.max_concurrent,
            batch_service=make_eval_batch_service(),
        )
