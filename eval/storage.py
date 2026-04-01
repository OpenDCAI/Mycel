"""SQLite storage for eval trajectories and metrics.

Database: ~/.leon/eval.db (separate from main leon.db)
"""

from __future__ import annotations

import json
from datetime import UTC
from pathlib import Path

from config.user_paths import user_home_path
from eval.models import (
    ObjectiveMetrics,
    RunTrajectory,
    SystemMetrics,
)
from eval.repo import SQLiteEvalRepo

_DEFAULT_DB_PATH = user_home_path("eval.db")


class TrajectoryStore:
    """SQLite-backed storage for eval trajectories and metrics."""

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path) if db_path else _DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._repo = SQLiteEvalRepo(self.db_path)
        self._init_db()

    def _init_db(self) -> None:
        self._repo.ensure_schema()

    def save_trajectory(self, trajectory: RunTrajectory) -> str:
        """Save a trajectory and its LLM/tool call records. Returns run_id."""
        trajectory_json = trajectory.model_dump_json()
        return self._repo.save_trajectory(trajectory, trajectory_json)

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
