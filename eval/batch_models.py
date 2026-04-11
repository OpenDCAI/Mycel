from __future__ import annotations

from pydantic import BaseModel, Field


class EvaluationBatch(BaseModel):
    batch_id: str
    kind: str
    submitted_by_user_id: str
    agent_user_id: str
    config_json: dict = Field(default_factory=dict)
    status: str = "pending"
    created_at: str = ""
    updated_at: str = ""
    summary_json: dict = Field(
        default_factory=lambda: {
            "total_runs": 0,
            "running_runs": 0,
            "completed_runs": 0,
            "failed_runs": 0,
        }
    )


class EvaluationBatchRun(BaseModel):
    batch_run_id: str
    batch_id: str
    item_key: str
    scenario_id: str
    status: str = "pending"
    thread_id: str | None = None
    eval_run_id: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    summary_json: dict = Field(default_factory=dict)
