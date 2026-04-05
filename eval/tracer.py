"""Trajectory tracer based on LangChain callback system.

Injected via config={"callbacks": [tracer]} into agent.astream().
Captures complete Run tree with LLM calls, tool calls, timing, and token usage.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from langchain_core.tracers.base import BaseTracer
from langchain_core.tracers.schemas import Run


class TrajectoryTracer(BaseTracer):
    """Capture agent execution trajectory via LangChain callback system.

    Lifecycle:
    1. Create instance with thread_id and user_message
    2. Inject into astream config: config={"callbacks": [tracer]}
    3. After execution, call to_trajectory() to extract RunTrajectory
    """

    name: str = "trajectory_tracer"

    def __init__(
        self,
        thread_id: str,
        user_message: str,
        cost_calculator: Any | None = None,
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        self.thread_id = thread_id
        self.user_message = user_message
        self.cost_calculator = cost_calculator
        self.traced_runs: list[Run] = []
        self._start_time = datetime.now(UTC)

    def _persist_run(self, run: Run) -> None:
        """Called when a root run completes. Collect the full Run tree."""
        self.traced_runs.append(run)

    def to_trajectory(self) -> RunTrajectory:
        """Convert collected Run trees into a RunTrajectory."""
        import json

        from eval.models import RunTrajectory

        llm_calls: list = []
        tool_calls: list = []
        final_response = ""
        run_tree_data: list[dict] = []

        for root_run in self.traced_runs:
            self._walk_run_tree(root_run, llm_calls, tool_calls)
            run_tree_data.append(self._run_to_dict(root_run))
            resp = self._extract_final_response(root_run)
            if resp:
                final_response = resp

        finished_at = datetime.now(UTC)

        return RunTrajectory(
            thread_id=self.thread_id,
            user_message=self.user_message,
            final_response=final_response,
            llm_calls=llm_calls,
            tool_calls=tool_calls,
            run_tree_json=json.dumps(run_tree_data, default=str, ensure_ascii=False),
            started_at=self._start_time.isoformat(),
            finished_at=finished_at.isoformat(),
            status="completed",
        )

    def enrich_from_runtime(self, trajectory: RunTrajectory, runtime: Any) -> None:
        """Enrich trajectory with token data from MonitorMiddleware runtime.

        Streaming mode doesn't populate Run.outputs with usage_metadata,
        so we distribute runtime aggregate tokens evenly across LLM calls.
        """
        if not runtime or not hasattr(runtime, "token"):
            return
        token = runtime.token
        if token.total_tokens == 0:
            return

        n = len(trajectory.llm_calls)
        if n == 0:
            return

        model_name = getattr(runtime, "_model_name", "")
        if not model_name:
            # Try to get from config
            model_name = ""

        per_call_input = token.input_tokens // n
        per_call_output = token.output_tokens // n
        per_call_total = token.total_tokens // n
        per_call_reasoning = token.reasoning_tokens // n
        per_call_cache_read = token.cache_read_tokens // n
        per_call_cache_write = token.cache_write_tokens // n

        cost_per_call = 0.0
        if token.cost_calculator:
            total_cost = float(token.get_cost().get("total", 0))
            cost_per_call = total_cost / n

        for call in trajectory.llm_calls:
            call.input_tokens = per_call_input
            call.output_tokens = per_call_output
            call.total_tokens = per_call_total
            call.reasoning_tokens = per_call_reasoning
            call.cache_read_tokens = per_call_cache_read
            call.cache_write_tokens = per_call_cache_write
            call.cost_usd = cost_per_call

    def _walk_run_tree(
        self,
        run: Run,
        llm_calls: list,
        tool_calls: list,
    ) -> None:
        """Recursively walk Run tree, extracting LLM and tool call records."""
        if run.run_type in ("chat_model", "llm"):
            record = self._extract_llm_record(run)
            if record:
                llm_calls.append(record)
        elif run.run_type == "tool":
            record = self._extract_tool_record(run)
            if record:
                tool_calls.append(record)

        for child in run.child_runs:
            self._walk_run_tree(child, llm_calls, tool_calls)

    def _extract_llm_record(self, run: Run) -> LLMCallRecord | None:
        """Extract LLMCallRecord from a chat_model Run."""
        from eval.models import LLMCallRecord

        duration_ms = self._calc_duration_ms(run)
        run_id = str(run.id)
        parent_run_id = str(run.parent_run_id) if run.parent_run_id else None

        input_tokens = output_tokens = reasoning_tokens = 0
        cache_read_tokens = cache_write_tokens = total_tokens = 0
        model_name = ""
        tool_calls_requested = 0
        cost_usd = 0.0

        if run.outputs:
            generations = run.outputs.get("generations", [[]])
            if generations and generations[0]:
                gen = generations[0][0]
                message = gen.get("message") if isinstance(gen, dict) else getattr(gen, "message", None)
                if message:
                    usage = getattr(message, "usage_metadata", None)
                    if usage:
                        input_tokens = usage.get("input_tokens", 0) or 0
                        output_tokens = usage.get("output_tokens", 0) or 0
                        total_tokens = usage.get("total_tokens", 0) or 0
                        input_details = usage.get("input_token_details", {}) or {}
                        output_details = usage.get("output_token_details", {}) or {}
                        cache_read_tokens = input_details.get("cache_read", 0) or 0
                        cache_write_tokens = input_details.get("cache_creation", 0) or 0
                        reasoning_tokens = output_details.get("reasoning", 0) or 0

                    tc = getattr(message, "tool_calls", None)
                    if tc:
                        tool_calls_requested = len(tc)

                    resp_meta = getattr(message, "response_metadata", {}) or {}
                    model_name = resp_meta.get("model_name", "") or resp_meta.get("model", "") or ""

            # Fallback: extract from llm_output (OpenAI format)
            if total_tokens == 0:
                llm_output = run.outputs.get("llm_output") or {}
                token_usage = llm_output.get("token_usage") or {}
                if token_usage:
                    input_tokens = token_usage.get("prompt_tokens", 0) or 0
                    output_tokens = token_usage.get("completion_tokens", 0) or 0
                    total_tokens = token_usage.get("total_tokens", 0) or 0
                    reasoning_tokens = token_usage.get("reasoning_tokens", 0) or 0
                if not model_name:
                    model_name = llm_output.get("model_name", "") or ""

        if self.cost_calculator and total_tokens > 0:
            token_dict = {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "reasoning_tokens": reasoning_tokens,
                "cache_read_tokens": cache_read_tokens,
                "cache_write_tokens": cache_write_tokens,
            }
            cost_result = self.cost_calculator.calculate(token_dict)
            cost_usd = float(cost_result.get("total", 0))

        return LLMCallRecord(
            run_id=run_id,
            parent_run_id=parent_run_id,
            model_name=model_name,
            duration_ms=duration_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            reasoning_tokens=reasoning_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_write_tokens=cache_write_tokens,
            total_tokens=total_tokens,
            cost_usd=cost_usd,
            tool_calls_requested=tool_calls_requested,
        )

    def _extract_tool_record(self, run: Run) -> ToolCallRecord | None:
        """Extract ToolCallRecord from a tool Run."""
        import json

        from eval.models import ToolCallRecord

        duration_ms = self._calc_duration_ms(run)
        run_id = str(run.id)
        parent_run_id = str(run.parent_run_id) if run.parent_run_id else None

        tool_name = run.name or ""
        tool_call_id = ""
        success = run.error is None
        error = run.error

        args_summary = ""
        if run.inputs:
            args_str = json.dumps(run.inputs, default=str, ensure_ascii=False)
            args_summary = args_str[:500] if len(args_str) > 500 else args_str

        result_summary = ""
        if run.outputs:
            out_str = json.dumps(run.outputs, default=str, ensure_ascii=False)
            result_summary = out_str[:500] if len(out_str) > 500 else out_str

        return ToolCallRecord(
            run_id=run_id,
            parent_run_id=parent_run_id,
            tool_name=tool_name,
            tool_call_id=tool_call_id,
            duration_ms=duration_ms,
            success=success,
            error=error,
            args_summary=args_summary,
            result_summary=result_summary,
        )

    def _extract_final_response(self, run: Run) -> str:
        """Extract final text response from Run outputs."""
        if not run.outputs:
            return ""
        messages = run.outputs.get("messages", [])
        if not messages:
            generations = run.outputs.get("generations", [[]])
            if generations and generations[0]:
                gen = generations[0][-1]
                msg = gen.get("message") if isinstance(gen, dict) else getattr(gen, "message", None)
                if msg:
                    content = getattr(msg, "content", "")
                    if isinstance(content, str):
                        return content
                    if isinstance(content, list):
                        return "".join(
                            block.get("text", "") if isinstance(block, dict) else str(block) for block in content
                        )
            return ""
        for msg in reversed(messages):
            if msg.__class__.__name__ in ("AIMessage", "AIMessageChunk"):
                content = getattr(msg, "content", "")
                if isinstance(content, str):
                    return content
                if isinstance(content, list):
                    return "".join(
                        block.get("text", "") if isinstance(block, dict) else str(block) for block in content
                    )
        return ""

    @staticmethod
    def _calc_duration_ms(run: Run) -> float:
        """Calculate duration in milliseconds from Run timestamps."""
        if run.start_time and run.end_time:
            delta = run.end_time - run.start_time
            return delta.total_seconds() * 1000
        return 0.0

    @staticmethod
    def _run_to_dict(run: Run) -> dict:
        """Convert Run to a serializable dict for run_tree_json."""
        return {
            "id": str(run.id),
            "name": run.name,
            "run_type": run.run_type,
            "start_time": run.start_time.isoformat() if run.start_time else None,
            "end_time": run.end_time.isoformat() if run.end_time else None,
            "error": run.error,
            "child_runs": [TrajectoryTracer._run_to_dict(c) for c in run.child_runs],
        }
