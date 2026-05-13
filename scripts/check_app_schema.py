#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = REPO_ROOT / "storage/schema"
MANIFEST_PATH = SCHEMA_DIR / "app_schema_manifest.json"

CREATE_SCHEMA_RE = re.compile(r"^CREATE SCHEMA (?P<name>[a-z_][a-z0-9_]*)", re.MULTILINE)
CREATE_TABLE_RE = re.compile(r"^CREATE TABLE (?P<name>[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*) \(", re.MULTILINE)
CREATE_FUNCTION_RE = re.compile(r"^CREATE FUNCTION (?P<name>[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*)\(", re.MULTILINE)

FORBIDDEN_BASELINE_TEXT = [
    "OWNER TO",
    "GRANT ",
    "CREATE ROLE",
    "CREATE DATABASE",
    "ALTER DEFAULT PRIVILEGES",
]

FORBIDDEN_SCHEMA_TEXT = [
    "deleted_for",
    "local_communication",
]


def _read_manifest(path: Path = MANIFEST_PATH) -> tuple[dict[str, Any] | None, list[str]]:
    if not path.is_file():
        return None, [f"missing schema manifest: {path.relative_to(REPO_ROOT)}"]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, [f"invalid schema manifest json: {path.relative_to(REPO_ROOT)}:{exc.lineno}:{exc.colno}: {exc.msg}"]
    if not isinstance(data, dict):
        return None, [f"schema manifest must be a JSON object: {path.relative_to(REPO_ROOT)}"]
    return data, []


def _string_list(data: dict[str, Any], key: str) -> tuple[list[str], list[str]]:
    value = data.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        return [], [f"schema manifest field {key!r} must be a non-empty string list"]
    return value, []


def check_schema_tree(repo_root: Path = REPO_ROOT) -> list[str]:
    schema_dir = repo_root / "storage/schema"
    manifest_path = schema_dir / "app_schema_manifest.json"
    violations: list[str] = []

    schema_subdirs = sorted(path.relative_to(repo_root).as_posix() for path in schema_dir.iterdir() if path.is_dir())
    if schema_subdirs:
        violations.append(f"schema directory must be flat; found subdirectories: {', '.join(schema_subdirs)}")
    rejected_schema_fork_path = schema_dir / "local_communication.sql"
    if rejected_schema_fork_path.exists():
        violations.append(f"forbidden schema fork path exists: {rejected_schema_fork_path.relative_to(repo_root)}")

    manifest, manifest_errors = _read_manifest(manifest_path)
    violations.extend(manifest_errors)
    if manifest is None:
        return violations

    baseline_name = manifest.get("baseline")
    if not isinstance(baseline_name, str) or not baseline_name.endswith(".sql"):
        violations.append("schema manifest field 'baseline' must name a .sql file")
        return violations

    patches, patch_errors = _string_list(manifest, "patches")
    schemas, schema_errors = _string_list(manifest, "app_owned_schemas")
    violations.extend(patch_errors)
    violations.extend(schema_errors)
    if patch_errors or schema_errors:
        return violations

    expected_files = {baseline_name, *patches}
    actual_sql_files = {path.name for path in schema_dir.glob("*.sql")}
    extra_files = sorted(actual_sql_files - expected_files)
    missing_files = sorted(expected_files - actual_sql_files)
    if extra_files:
        violations.append(f"schema SQL files missing from manifest: {', '.join(extra_files)}")
    if missing_files:
        violations.append(f"schema manifest references missing SQL files: {', '.join(missing_files)}")

    baseline_path = schema_dir / baseline_name
    if not baseline_path.is_file():
        return violations

    baseline_sql = baseline_path.read_text(encoding="utf-8")
    schema_sql = "\n".join(path.read_text(encoding="utf-8") for path in sorted(schema_dir.glob("*.sql")))

    for needle in FORBIDDEN_BASELINE_TEXT:
        if needle in baseline_sql:
            violations.append(f"baseline contains deployment-specific SQL token: {needle}")
    for needle in FORBIDDEN_SCHEMA_TEXT:
        if needle in schema_sql:
            violations.append(f"schema tree contains rejected local fork residue token: {needle}")

    baseline_schemas = sorted(CREATE_SCHEMA_RE.findall(baseline_sql))
    expected_schemas = sorted(schemas)
    if baseline_schemas != expected_schemas:
        violations.append(f"baseline schemas differ from manifest: expected {expected_schemas}, found {baseline_schemas}")

    baseline_tables = sorted(CREATE_TABLE_RE.findall(baseline_sql))
    table_count = manifest.get("baseline_table_count")
    if not isinstance(table_count, int) or len(baseline_tables) != table_count:
        violations.append(f"baseline table count differs from manifest: expected {table_count}, found {len(baseline_tables)}")

    baseline_functions = sorted(CREATE_FUNCTION_RE.findall(baseline_sql))
    function_count = manifest.get("baseline_function_count")
    if not isinstance(function_count, int) or len(baseline_functions) != function_count:
        violations.append(f"baseline function count differs from manifest: expected {function_count}, found {len(baseline_functions)}")

    return violations


def main() -> int:
    violations = check_schema_tree()
    if violations:
        print("App schema check failed:")
        for violation in violations:
            print(f"- {violation}")
        return 1
    print("App schema check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
