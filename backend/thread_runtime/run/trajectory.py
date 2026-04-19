"""Trajectory tracing scope for thread runtime runs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass
class TrajectoryScope:
    tracer: Any
    store: Any
    run_id: str

    def inject_callback(self, config: dict[str, Any]) -> None:
        config.setdefault("callbacks", []).append(self.tracer)

    def finalize_success(self, *, agent: Any, trajectory_status: str) -> None:
        from eval.collector import MetricsCollector

        trajectory = self.tracer.to_trajectory()
        runtime_status = agent.runtime.get_status_dict() if hasattr(agent, "runtime") else None
        if hasattr(agent, "runtime"):
            self.tracer.enrich_from_runtime(trajectory, agent.runtime)
        finalized = trajectory.model_copy(update={"status": trajectory_status})
        system_metrics, objective_metrics = MetricsCollector().compute_all(finalized, runtime_status)
        self.store.finalize_run(
            run_id=self.run_id,
            finished_at=trajectory.finished_at,
            final_response=trajectory.final_response,
            status=trajectory_status,
            run_tree_json=trajectory.run_tree_json,
            trajectory_json=finalized.model_dump_json(),
        )
        self.store.save_metrics(self.run_id, "system", system_metrics)
        self.store.save_metrics(self.run_id, "objective", objective_metrics)

    def finalize_cancelled(self) -> None:
        trajectory = self.tracer.to_trajectory()
        self.store.finalize_run(
            run_id=self.run_id,
            finished_at=datetime.now(UTC).isoformat(),
            final_response=trajectory.final_response,
            status="cancelled",
            run_tree_json=trajectory.run_tree_json,
            trajectory_json=trajectory.model_copy(update={"status": "cancelled"}).model_dump_json(),
        )

    def finalize_error(self) -> None:
        trajectory = self.tracer.to_trajectory()
        self.store.finalize_run(
            run_id=self.run_id,
            finished_at=datetime.now(UTC).isoformat(),
            final_response=trajectory.final_response,
            status="error",
            run_tree_json=trajectory.run_tree_json,
            trajectory_json=trajectory.model_copy(update={"status": "error"}).model_dump_json(),
        )


def build_trajectory_scope(
    *,
    agent: Any,
    thread_id: str,
    run_id: str,
    user_message: str,
    enable_trajectory: bool,
) -> TrajectoryScope | None:
    if not enable_trajectory:
        return None
    try:
        from eval.storage import TrajectoryStore
        from eval.tracer import TrajectoryTracer

        cost_calc = getattr(
            getattr(getattr(agent, "runtime", None), "token", None),
            "cost_calculator",
            None,
        )
        tracer = TrajectoryTracer(
            thread_id=thread_id,
            user_message=user_message,
            run_id=run_id,
            cost_calculator=cost_calc,
        )
        store = TrajectoryStore()
        store.upsert_run_header(
            run_id=run_id,
            thread_id=thread_id,
            started_at=tracer._start_time.isoformat(),
            user_message=user_message,
            status="running",
        )
        return TrajectoryScope(tracer=tracer, store=store, run_id=run_id)
    except ImportError:
        return None
