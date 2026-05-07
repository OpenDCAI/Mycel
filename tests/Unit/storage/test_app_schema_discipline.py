from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CHECKER_PATH = ROOT / "scripts/check_app_schema.py"
SCHEMA_DIR = ROOT / "storage/schema"


def _load_checker():
    spec = importlib.util.spec_from_file_location("check_app_schema", CHECKER_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_schema_manifest_names_the_runtime_baseline_and_all_patch_sql_files() -> None:
    manifest = json.loads((SCHEMA_DIR / "app_schema_manifest.json").read_text(encoding="utf-8"))

    expected_files = {manifest["baseline"], *manifest["patches"]}
    actual_files = {path.name for path in SCHEMA_DIR.glob("*.sql")}

    assert manifest["baseline"] == "app_schema.sql"
    assert actual_files == expected_files
    assert "local_communication.sql" not in actual_files


def test_runtime_baseline_is_current_app_schema_not_a_local_only_fork() -> None:
    baseline = (SCHEMA_DIR / "app_schema.sql").read_text(encoding="utf-8")
    manifest = json.loads((SCHEMA_DIR / "app_schema_manifest.json").read_text(encoding="utf-8"))

    assert "CREATE SCHEMA identity;" in baseline
    assert "CREATE SCHEMA chat;" in baseline
    assert "CREATE SCHEMA agent;" in baseline
    assert "CREATE TABLE identity.users" in baseline
    assert "CREATE TABLE chat.messages" in baseline
    assert "CREATE TABLE agent.threads" in baseline
    assert "CREATE TABLE container.sandboxes" in baseline
    assert "CREATE TABLE library.skills" in baseline
    assert "CREATE TABLE observability.provider_events" in baseline
    assert baseline.count("CREATE TABLE ") == manifest["baseline_table_count"]
    assert baseline.count("CREATE FUNCTION ") == manifest["baseline_function_count"]
    assert "local_communication" not in baseline
    assert "deleted_for" not in baseline


def test_app_schema_checker_passes_current_tree() -> None:
    checker = _load_checker()

    assert checker.check_schema_tree(ROOT) == []


def test_app_schema_checker_rejects_schema_subdirectories(tmp_path) -> None:
    checker = _load_checker()
    schema_dir = tmp_path / "storage" / "schema"
    schema_dir.mkdir(parents=True)
    (schema_dir / "nested").mkdir()
    (schema_dir / "app_schema_manifest.json").write_text(
        '{"baseline": "app_schema.sql", "patches": [], "app_owned_schemas": ["identity"], '
        '"baseline_table_count": 0, "baseline_function_count": 0}',
        encoding="utf-8",
    )
    (schema_dir / "app_schema.sql").write_text("CREATE SCHEMA identity;", encoding="utf-8")

    violations = checker.check_schema_tree(tmp_path)

    assert violations == ["schema directory must be flat; found subdirectories: storage/schema/nested"]


def test_app_schema_checker_is_a_loud_cli_gate() -> None:
    result = subprocess.run(
        [sys.executable, str(CHECKER_PATH)],
        cwd=ROOT,
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "App schema check passed."
