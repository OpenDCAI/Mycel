"""Concurrent test execution engine for eval scenarios."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from eval.collector import MetricsCollector
from eval.harness.client import EvalClient
from eval.models import EvalResult, EvalScenario, TrajectoryCapture
from eval.storage import TrajectoryStore


class EvalRunner:
    """Run eval scenarios against a Leon backend instance."""

    def __init__(
        self,
        client: EvalClient,
        store: TrajectoryStore | None = None,
        collector: MetricsCollector | None = None,
    ):
        self.client = client
        self.store = store
        self.collector = collector or MetricsCollector()

    async def run_scenario(self, scenario: EvalScenario) -> EvalResult:
        """Execute a single scenario end-to-end."""
        thread_id = await self.client.create_thread(sandbox=scenario.sandbox)
        captures: list[TrajectoryCapture] = []
        started_at = datetime.now(UTC)

        try:
            for msg in scenario.messages:
                if msg.delay_seconds > 0:
                    await asyncio.sleep(msg.delay_seconds)
                capture = await asyncio.wait_for(
                    self.client.run_message(thread_id, msg.content, enable_trajectory=True),
                    timeout=scenario.timeout_seconds,
                )
                captures.append(capture)

            # Get final runtime status
            runtime_status = None
            try:
                runtime_status = await self.client.get_runtime(thread_id)
            except Exception:
                pass

            finished_at = datetime.now(UTC)

            # Build trajectory from captures
            trajectory = self._build_trajectory(
                thread_id=thread_id,
                user_message=scenario.messages[0].content if scenario.messages else "",
                captures=captures,
                started_at=started_at.isoformat(),
                finished_at=finished_at.isoformat(),
            )

            # Compute metrics
            sys_metrics, obj_metrics = self.collector.compute_all(trajectory, runtime_status)

            # Persist if store available
            if self.store:
                self.store.save_trajectory(trajectory)
                self.store.save_metrics(trajectory.id, "system", sys_metrics)
                self.store.save_metrics(trajectory.id, "objective", obj_metrics)

            return EvalResult(
                scenario_id=scenario.id,
                trajectory=trajectory,
                system_metrics=sys_metrics,
                objective_metrics=obj_metrics,
            )
        finally:
            try:
                await self.client.delete_thread(thread_id)
            except Exception:
                pass

    async def run_all(
        self,
        scenarios: list[EvalScenario],
        max_concurrent: int = 3,
    ) -> list[EvalResult]:
        """Run multiple scenarios with concurrency control."""
        semaphore = asyncio.Semaphore(max_concurrent)
        results: list[EvalResult] = []

        async def _run_with_sem(s: EvalScenario) -> EvalResult:
            async with semaphore:
                return await self.run_scenario(s)

        tasks = [asyncio.create_task(_run_with_sem(s)) for s in scenarios]
        for task in asyncio.as_completed(tasks):
            result = await task
            results.append(result)

        return results

    @staticmethod
    def _build_trajectory(
        thread_id: str,
        user_message: str,
        captures: list[TrajectoryCapture],
        started_at: str,
        finished_at: str,
    ) -> RunTrajectory:
        """Merge multiple TrajectoryCaptures into a single RunTrajectory."""
        from eval.models import LLMCallRecord, RunTrajectory, ToolCallRecord

        all_text: list[str] = []
        tool_records: list[ToolCallRecord] = []
        final_status: dict = {}

        # Build tool_call_id → result lookup
        result_map: dict[str, dict] = {}
        for cap in captures:
            for tr in cap.tool_results:
                tcid = tr.get("tool_call_id", "")
                if tcid:
                    result_map[tcid] = tr

        for cap in captures:
            all_text.extend(cap.text_chunks)
            if cap.final_status:
                final_status = cap.final_status

            for tc in cap.tool_calls:
                tcid = tc.get("id", "")
                name = tc.get("name", "unknown")
                result = result_map.get(tcid, {})
                content = result.get("content", "")
                is_error = "error" in content.lower() if content else False
                tool_records.append(
                    ToolCallRecord(
                        run_id=tcid,
                        tool_name=name,
                        tool_call_id=tcid,
                        success=not is_error,
                        error=content[:200] if is_error else None,
                        args_summary=str(tc.get("args", ""))[:200],
                        result_summary=content[:200] if content else "",
                    )
                )

        # Extract token data from final status snapshot
        llm_records: list[LLMCallRecord] = []
        tokens = final_status.get("tokens", {})
        total_tokens = tokens.get("total_tokens", 0)
        if total_tokens > 0:
            llm_records.append(
                LLMCallRecord(
                    run_id=thread_id,
                    input_tokens=tokens.get("input_tokens", 0),
                    output_tokens=tokens.get("output_tokens", 0),
                    reasoning_tokens=tokens.get("reasoning_tokens", 0),
                    cache_read_tokens=tokens.get("cache_read_tokens", 0),
                    cache_write_tokens=tokens.get("cache_write_tokens", 0),
                    total_tokens=total_tokens,
                    cost_usd=tokens.get("total_cost_usd", 0.0),
                )
            )

        final_response = "".join(all_text)
        status = "completed"
        for cap in captures:
            if cap.terminal_event == "error":
                status = "error"
                break
            if cap.terminal_event == "cancelled":
                status = "cancelled"
                break

        return RunTrajectory(
            thread_id=thread_id,
            user_message=user_message,
            final_response=final_response,
            llm_calls=llm_records,
            tool_calls=tool_records,
            started_at=started_at,
            finished_at=finished_at,
            status=status,
        )


async def _main() -> None:
    """CLI entry point for running eval scenarios."""
    import argparse
    import sys
    from pathlib import Path

    from eval.harness.scenario import load_scenario, load_scenarios_from_dir

    parser = argparse.ArgumentParser(description="Leon Eval Runner")
    parser.add_argument("--scenario", type=str, help="Path to a single scenario YAML")
    parser.add_argument("--scenario-dir", type=str, help="Path to scenario directory")
    parser.add_argument("--base-url", type=str, default="http://localhost:8001")
    parser.add_argument("--max-concurrent", type=int, default=3)
    args = parser.parse_args()

    scenarios: list[EvalScenario] = []
    if args.scenario:
        scenarios.append(load_scenario(args.scenario))
    elif args.scenario_dir:
        scenarios = load_scenarios_from_dir(args.scenario_dir)
    else:
        # Default: look for eval/scenarios/
        default_dir = Path(__file__).parent.parent / "scenarios"
        if default_dir.exists():
            scenarios = load_scenarios_from_dir(default_dir)

    if not scenarios:
        print("No scenarios found.")
        sys.exit(1)

    print(f"Running {len(scenarios)} scenario(s) against {args.base_url}")

    client = EvalClient(base_url=args.base_url)
    store = TrajectoryStore()
    runner = EvalRunner(client=client, store=store)

    try:
        results = await runner.run_all(scenarios, max_concurrent=args.max_concurrent)
        for r in results:
            print(f"\n--- {r.scenario_id} ---")
            print(f"  Status: {r.trajectory.status}")
            print(f"  LLM calls: {r.system_metrics.llm_call_count}")
            print(f"  Tool calls: {r.system_metrics.tool_call_count}")
            print(f"  Tokens: {r.system_metrics.total_tokens}")
            print(f"  Cost: ${r.system_metrics.total_cost_usd:.4f}")
            print(f"  Duration: {r.objective_metrics.total_duration_ms:.0f}ms")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(_main())
