from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from eval.models import EvalScenario


@dataclass(frozen=True)
class EvaluationJobSpec:
    batch_id: str
    scenarios: list[EvalScenario]
    execution_base_url: str
    token: str
    agent_user_id: str


class EvaluationJobScheduler(Protocol):
    def submit(self, spec: EvaluationJobSpec) -> None: ...
