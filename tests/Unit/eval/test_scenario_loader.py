from pathlib import Path

import pytest

from eval.harness import scenario as scenario_loader


def test_load_scenario_parses_benchmark_contract(tmp_path: Path) -> None:
    yaml_path = tmp_path / "scenario.yaml"
    yaml_path.write_text(
        """
id: benchmark-scenario
name: Benchmark Scenario
category: swe
sandbox: local
messages:
  - content: "hello"
benchmark:
  family: swe-bench
  name: SWE-bench Verified
  split: smoke
  instance_id: astropy__astropy-12907
workspace:
  cwd: /workspace/project
  repo: astropy/astropy
  base_commit: abc123
judge_config:
  type: command
  config:
    command: ["python", "judge.py"]
artifacts:
  requested_artifacts: ["patch", "test_log"]
export:
  format: swe-bench-predictions
  key: smoke-export
""".strip()
    )

    loaded = scenario_loader.load_scenario(yaml_path)

    assert loaded.benchmark is not None
    assert loaded.benchmark.family == "swe-bench"
    assert loaded.benchmark.instance_id == "astropy__astropy-12907"
    assert loaded.workspace is not None
    assert loaded.workspace.cwd == "/workspace/project"
    assert loaded.judge_config is not None
    assert loaded.judge_config.type == "command"
    assert loaded.artifact_policy is not None
    assert loaded.artifact_policy.requested_artifacts == ["patch", "test_log"]
    assert loaded.export is not None
    assert loaded.export.format == "swe-bench-predictions"


def test_load_scenarios_from_dirs_rejects_duplicate_ids(tmp_path: Path) -> None:
    first = tmp_path / "one"
    second = tmp_path / "two"
    first.mkdir()
    second.mkdir()
    (first / "a.yaml").write_text("id: duplicated\nname: One\nmessages: []\n")
    (second / "b.yaml").write_text("id: duplicated\nname: Two\nmessages: []\n")

    with pytest.raises(ValueError, match="Duplicate evaluation scenario id"):
        scenario_loader.load_scenarios_from_dirs([first, second])


def test_parse_scenario_dirs_uses_env_style_separator(tmp_path: Path) -> None:
    first = tmp_path / "a"
    second = tmp_path / "b"

    parsed = scenario_loader.parse_scenario_dirs(
        f"{first}{scenario_loader.os.pathsep}{second}",
        default_dirs=[],
    )

    assert parsed == [first, second]
