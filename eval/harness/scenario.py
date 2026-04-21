"""Scenario definition and YAML loading."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from eval.models import ArtifactPolicy, BenchmarkInfo, EvalScenario, ExportConfig, JudgeConfig, ScenarioMessage, WorkspaceSpec


def load_scenario(path: str | Path) -> EvalScenario:
    """Load a single scenario from a YAML file."""
    path = Path(path)
    with path.open() as f:
        raw = yaml.safe_load(f)

    messages = [
        ScenarioMessage(
            content=m if isinstance(m, str) else m.get("content", ""),
            delay_seconds=m.get("delay_seconds", 0.0) if isinstance(m, dict) else 0.0,
        )
        for m in raw.get("messages", [])
    ]

    return EvalScenario(
        id=raw["id"],
        name=raw["name"],
        category=raw.get("category", ""),
        timeout_seconds=raw.get("timeout_seconds", 120),
        sandbox=raw.get("sandbox", "local"),
        messages=messages,
        expected_behaviors=raw.get("expected_behaviors", []),
        evaluation_criteria=raw.get("evaluation_criteria", []),
        benchmark=BenchmarkInfo.model_validate(raw["benchmark"]) if raw.get("benchmark") else None,
        workspace=WorkspaceSpec.model_validate(raw["workspace"]) if raw.get("workspace") else None,
        judge_config=JudgeConfig.model_validate(raw.get("judge_config") or raw.get("judge"))
        if raw.get("judge_config") or raw.get("judge")
        else None,
        artifact_policy=ArtifactPolicy.model_validate(raw.get("artifact_policy") or raw.get("artifacts"))
        if raw.get("artifact_policy") or raw.get("artifacts")
        else None,
        export=ExportConfig.model_validate(raw["export"]) if raw.get("export") else None,
    )


def load_scenarios_from_dir(dir_path: str | Path) -> list[EvalScenario]:
    """Load all *.yaml scenarios from a directory."""
    dir_path = Path(dir_path)
    scenarios = []
    for yaml_file in sorted(dir_path.glob("*.yaml")):
        scenarios.append(load_scenario(yaml_file))
    return scenarios


def load_scenarios_from_dirs(dir_paths: list[str | Path]) -> list[EvalScenario]:
    """Load scenarios from multiple directories, preserving stable order and unique ids."""
    scenarios: list[EvalScenario] = []
    seen_ids: dict[str, Path] = {}
    for raw_dir in dir_paths:
        dir_path = Path(raw_dir)
        if not dir_path.exists():
            continue
        for yaml_file in sorted(dir_path.rglob("*.yaml")):
            scenario = load_scenario(yaml_file)
            existing = seen_ids.get(scenario.id)
            if existing is not None:
                raise ValueError(f"Duplicate evaluation scenario id {scenario.id!r} in {yaml_file} and {existing}")
            seen_ids[scenario.id] = yaml_file
            scenarios.append(scenario)
    return scenarios


def parse_scenario_dirs(raw_value: str | None, *, default_dirs: list[Path]) -> list[Path]:
    """Parse LEON_EVAL_SCENARIO_DIRS style path lists."""
    if not raw_value:
        return list(default_dirs)
    return [Path(part).expanduser() for part in raw_value.split(os.pathsep) if part.strip()]
