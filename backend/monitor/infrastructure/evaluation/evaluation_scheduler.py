"""Evaluation job scheduling contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from eval.models import EvalScenario


@dataclass(frozen=True)
class EvaluationJobSpec:
    batch_id: str
    scenarios: list[EvalScenario]
    base_url: str
    token: str
    agent_user_id: str
    max_concurrent: int = 1


class EvaluationJobScheduler(Protocol):
    def submit(self, spec: EvaluationJobSpec) -> None: ...
