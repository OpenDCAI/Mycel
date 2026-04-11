from __future__ import annotations

from eval.models import EvalResult, EvalScenario


class EvaluationBatchExecutor:
    def __init__(self, *, runner, batch_service) -> None:
        self._runner = runner
        self._batch_service = batch_service

    async def run_batch(self, batch_id: str, scenarios: list[EvalScenario]) -> list[EvalResult]:
        self._batch_service.update_batch_status(batch_id, "running")
        results: list[EvalResult] = []
        try:
            for scenario in scenarios:
                self._batch_service.mark_batch_run_running_for_scenario(batch_id, scenario.id)
                try:
                    result = await self._runner.run_scenario(scenario)
                except Exception as exc:
                    self._batch_service.record_eval_error(batch_id, scenario.id, exc)
                    raise
                self._batch_service.record_eval_result(batch_id, result)
                results.append(result)
        except Exception:
            self._batch_service.update_batch_status(batch_id, "failed")
            raise
        self._batch_service.update_batch_status(batch_id, "completed")
        return results
