"""Judge registry and implementations for benchmark-aware evaluation."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shlex
import subprocess
from collections.abc import Sequence

from eval.models import EvalResult, EvalScenario, JudgeConfig, JudgeResult

logger = logging.getLogger(__name__)


class NoopJudge:
    async def evaluate(self, scenario: EvalScenario, result: EvalResult) -> JudgeResult:
        verdict = "passed" if result.trajectory.status == "completed" else "failed"
        return JudgeResult(
            judge_type="noop",
            status="completed",
            verdict=verdict,
            rationale="No judge configured; falling back to runtime completion status.",
            scores={"completion": 1.0 if verdict == "passed" else 0.0},
            metadata={"scenario_id": scenario.id},
        )


class HeuristicJudge:
    def __init__(self, config: dict[str, object]) -> None:
        self._config = config

    async def evaluate(self, scenario: EvalScenario, result: EvalResult) -> JudgeResult:
        response = result.trajectory.final_response or ""
        case_sensitive = bool(self._config.get("case_sensitive", False))
        threshold = float(self._config.get("pass_threshold", 1.0))
        required = list(self._config.get("required_substrings") or [])
        if not required:
            required = [*scenario.expected_behaviors, *scenario.evaluation_criteria]

        if not case_sensitive:
            haystack = response.lower()
            required = [str(item).lower() for item in required]
        else:
            haystack = response
            required = [str(item) for item in required]

        if not required:
            matched = 1
            total = 1
        else:
            matched = sum(1 for item in required if item and item in haystack)
            total = len(required)
        score = matched / total if total else 0.0
        verdict = "passed" if score >= threshold else "failed"
        return JudgeResult(
            judge_type="heuristic",
            status="completed",
            verdict=verdict,
            rationale=f"Matched {matched}/{total} required checks.",
            scores={"pass_rate": score, "resolved": 1.0 if verdict == "passed" else 0.0},
            metadata={"required_checks": required, "pass_threshold": threshold},
        )


class CommandJudge:
    def __init__(self, config: dict[str, object]) -> None:
        command = config.get("command")
        if isinstance(command, str):
            self._command = shlex.split(command)
        elif isinstance(command, Sequence):
            self._command = [str(item) for item in command]
        else:
            raise ValueError("command judge requires a non-empty command")
        if not self._command:
            raise ValueError("command judge requires a non-empty command")
        self._cwd = str(config.get("cwd") or "").strip() or None
        self._timeout_seconds = float(config.get("timeout_seconds") or 60)
        self._env = {str(key): str(value) for key, value in dict(config.get("env") or {}).items()}

    async def evaluate(self, scenario: EvalScenario, result: EvalResult) -> JudgeResult:
        payload = {
            "scenario": {
                "id": scenario.id,
                "name": scenario.name,
                "benchmark": scenario.benchmark.model_dump(mode="json") if scenario.benchmark else None,
                "workspace": scenario.workspace.model_dump(mode="json") if scenario.workspace else None,
            },
            "result": {
                "run_id": result.trajectory.id,
                "thread_id": result.trajectory.thread_id,
                "status": result.trajectory.status,
                "final_response": result.trajectory.final_response,
                "artifacts": [artifact.model_dump(mode="json") for artifact in result.artifacts],
            },
        }
        completed = await asyncio.to_thread(
            subprocess.run,
            self._command,
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            cwd=self._cwd,
            env={**os.environ, **self._env},
            timeout=self._timeout_seconds,
            check=False,
        )
        if completed.returncode != 0:
            logger.error("Command judge failed for scenario %s with exit code %s", scenario.id, completed.returncode)
            raise RuntimeError(f"Judge command failed with exit={completed.returncode}: {(completed.stderr or completed.stdout).strip()}")

        stdout = (completed.stdout or "").strip()
        parsed = json.loads(stdout) if stdout else {}
        if parsed and not isinstance(parsed, dict):
            raise RuntimeError("Judge command must emit a JSON object on stdout")
        return JudgeResult(
            judge_type="command",
            status=str(parsed.get("status") or "completed"),
            verdict=str(parsed.get("verdict") or "unknown"),
            rationale=str(parsed.get("rationale") or ""),
            scores={str(key): float(value) for key, value in dict(parsed.get("scores") or {}).items()},
            metadata=dict(parsed.get("metadata") or {}),
        )


def build_judge(judge_config: JudgeConfig | None) -> NoopJudge | HeuristicJudge | CommandJudge:
    if judge_config is None or judge_config.type == "noop":
        return NoopJudge()
    if judge_config.type == "heuristic":
        return HeuristicJudge(judge_config.config)
    if judge_config.type == "command":
        return CommandJudge(judge_config.config)
    raise ValueError(f"Unsupported evaluation judge type: {judge_config.type}")
