from __future__ import annotations

from eval.batch_service import EvaluationBatchService
from eval.storage import TrajectoryStore
from storage.runtime import build_evaluation_batch_repo


def make_trajectory_store() -> TrajectoryStore:
    return TrajectoryStore()


def make_eval_batch_service() -> EvaluationBatchService:
    return EvaluationBatchService(batch_repo=build_evaluation_batch_repo())
