"""Monitor evaluation read-source boundary."""

from __future__ import annotations

from backend.web.services import monitor_evaluation_storage_service


def make_trajectory_store():
    return monitor_evaluation_storage_service.make_trajectory_store()


def make_eval_batch_service():
    return monitor_evaluation_storage_service.make_eval_batch_service()
