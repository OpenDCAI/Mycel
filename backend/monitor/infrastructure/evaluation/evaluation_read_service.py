"""Monitor evaluation read-source boundary."""

from __future__ import annotations

from backend.monitor.infrastructure.evaluation import evaluation_storage_service


def make_trajectory_store():
    return evaluation_storage_service.make_trajectory_store()


def make_eval_batch_service():
    return evaluation_storage_service.make_eval_batch_service()
