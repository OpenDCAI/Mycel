from __future__ import annotations

import asyncio
import logging

from eval.models import EvalResult, EvalScenario

logger = logging.getLogger(__name__)


class EvaluationBatchExecutor:
    def __init__(self, *, runner, batch_service) -> None:
        self._runner = runner
        self._batch_service = batch_service

    async def run_batch(self, batch_id: str, scenarios: list[EvalScenario], *, max_concurrent: int = 1) -> list[EvalResult]:
        self._batch_service.update_batch_status(batch_id, "running")
        semaphore = asyncio.Semaphore(max(1, max_concurrent))
        results: list[EvalResult] = []
        failed_scenarios: list[str] = []

        async def _run_single_scenario(scenario: EvalScenario) -> EvalResult | None:
            async with semaphore:
                logger.info("Running evaluation scenario %s in batch %s", scenario.id, batch_id)
                self._batch_service.mark_batch_run_running_for_scenario(batch_id, scenario.id)
                try:
                    result = await self._runner.run_scenario(scenario)
                except Exception as exc:
                    logger.exception("Evaluation scenario %s failed in batch %s", scenario.id, batch_id)
                    self._batch_service.record_eval_error(batch_id, scenario.id, exc)
                    failed_scenarios.append(scenario.id)
                    return None
                self._batch_service.record_eval_result(batch_id, result)
                return result

        for task in asyncio.as_completed([asyncio.create_task(_run_single_scenario(scenario)) for scenario in scenarios]):
            result = await task
            if result is not None:
                results.append(result)

        final_status = "failed" if failed_scenarios else "completed"
        if failed_scenarios:
            logger.warning("Batch %s completed with failed scenarios: %s", batch_id, ", ".join(failed_scenarios))
        self._batch_service.update_batch_status(batch_id, final_status)
        return results
