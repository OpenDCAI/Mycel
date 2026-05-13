from __future__ import annotations

from uuid import uuid4

from pydantic import BaseModel, Field

# --- Trajectory records ---


class LLMCallRecord(BaseModel):
    run_id: str
    parent_run_id: str | None = None
    model_name: str = ""
    duration_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    tool_calls_requested: int = 0


class ToolCallRecord(BaseModel):
    run_id: str
    parent_run_id: str | None = None
    tool_name: str
    tool_call_id: str = ""
    duration_ms: float = 0.0
    success: bool = True
    error: str | None = None
    args_summary: str = ""
    result_summary: str = ""


class RunTrajectory(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    thread_id: str
    user_message: str
    final_response: str = ""
    llm_calls: list[LLMCallRecord] = Field(default_factory=list)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    run_tree_json: str = ""
    started_at: str = ""
    finished_at: str = ""
    status: str = "completed"


# --- Metrics: Tier 1 (System) ---


class SystemMetrics(BaseModel):
    total_tokens: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cache_hit_rate: float = 0.0
    context_usage_percent: float = 0.0
    message_count: int = 0
    llm_call_count: int = 0
    tool_call_count: int = 0
    total_cost_usd: float = 0.0


class ToolTimingStats(BaseModel):
    tool_name: str
    count: int = 0
    avg_ms: float = 0.0
    max_ms: float = 0.0
    p95_ms: float = 0.0
    success_rate: float = 1.0


# --- Metrics: Tier 2 (Objective) ---


class ObjectiveMetrics(BaseModel):
    tool_timing_stats: dict[str, ToolTimingStats] = Field(default_factory=dict)
    llm_latency_avg_ms: float = 0.0
    llm_latency_max_ms: float = 0.0
    llm_latency_p95_ms: float = 0.0
    total_duration_ms: float = 0.0
    tokens_per_second: float = 0.0
    tool_calls_per_llm_call: float = 0.0
    slow_operations: list[str] = Field(default_factory=list)


# --- Scenario definitions ---


class ScenarioMessage(BaseModel):
    content: str
    delay_seconds: float = 0.0


class EvalScenario(BaseModel):
    id: str
    name: str
    category: str = ""
    timeout_seconds: int = 120
    sandbox: str = "local"
    messages: list[ScenarioMessage] = Field(default_factory=list)
    expected_behaviors: list[str] = Field(default_factory=list)
    evaluation_criteria: list[str] = Field(default_factory=list)


# --- SSE stream capture ---


class TrajectoryCapture(BaseModel):
    text_chunks: list[str] = Field(default_factory=list)
    tool_calls: list[dict] = Field(default_factory=list)
    tool_results: list[dict] = Field(default_factory=list)
    status_snapshots: list[dict] = Field(default_factory=list)
    final_status: dict = Field(default_factory=dict)
    terminal_event: str = ""


# --- Eval result ---


class EvalResult(BaseModel):
    scenario_id: str
    trajectory: RunTrajectory
    system_metrics: SystemMetrics = Field(default_factory=SystemMetrics)
    objective_metrics: ObjectiveMetrics = Field(default_factory=ObjectiveMetrics)
