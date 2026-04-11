"""Storage for eval trajectories and metrics."""

from __future__ import annotations

import json
from datetime import UTC
from pathlib import Path

from eval.models import (
    ObjectiveMetrics,
    RunTrajectory,
    SystemMetrics,
)


class TrajectoryStore:
    """Storage for eval trajectories and metrics."""

    def __init__(self, db_path: str | Path | None = None, eval_repo=None):
        if eval_repo is not None:
            self._repo = eval_repo
        else:
            from storage.runtime import build_storage_container

            container = build_storage_container()
            self._repo = container.eval_repo()

    def save_trajectory(self, trajectory: RunTrajectory) -> str:
        """Save a trajectory and its LLM/tool call records. Returns run_id."""
        trajectory_json = trajectory.model_dump_json()
        return self._repo.save_trajectory(trajectory, trajectory_json)

    def upsert_run_header(
        self,
        *,
        run_id: str,
        thread_id: str,
        started_at: str,
        user_message: str,
        status: str,
    ) -> None:
        self._repo.upsert_run_header(
            run_id=run_id,
            thread_id=thread_id,
            started_at=started_at,
            user_message=user_message,
            status=status,
        )

    def finalize_run(
        self,
        *,
        run_id: str,
        finished_at: str,
        final_response: str,
        status: str,
        run_tree_json: str,
        trajectory_json: str,
    ) -> None:
        self._repo.finalize_run(
            run_id=run_id,
            finished_at=finished_at,
            final_response=final_response,
            status=status,
            run_tree_json=run_tree_json,
            trajectory_json=trajectory_json,
        )

    def save_metrics(
        self,
        run_id: str,
        tier: str,
        metrics: SystemMetrics | ObjectiveMetrics,
    ) -> None:
        """Save computed metrics for a run."""
        from datetime import datetime

        self._repo.save_metrics(
            run_id=run_id,
            tier=tier,
            timestamp=datetime.now(UTC).isoformat(),
            metrics_json=metrics.model_dump_json(),
        )

    def get_trajectory(self, run_id: str) -> RunTrajectory | None:
        """Load a trajectory by run_id."""
        trajectory_json = self._repo.get_trajectory_json(run_id)
        if not trajectory_json:
            return None
        return RunTrajectory.model_validate_json(trajectory_json)

    def get_run(self, run_id: str) -> dict | None:
        """Load one persisted run header by run_id."""
        return self._repo.get_run(run_id)

    def list_runs(self, thread_id: str | None = None, limit: int = 50) -> list[dict]:
        """List eval runs, optionally filtered by thread_id."""
        return self._repo.list_runs(thread_id=thread_id, limit=limit)

    def get_metrics(self, run_id: str, tier: str | None = None) -> list[dict]:
        """Get metrics for a run, optionally filtered by tier."""
        rows = self._repo.get_metrics(run_id=run_id, tier=tier)
        result = []
        for d in rows:
            if d.get("metrics_json"):
                d["metrics"] = json.loads(d["metrics_json"])
                del d["metrics_json"]
            result.append(d)
        return result
