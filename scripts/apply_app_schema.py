#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = REPO_ROOT / "storage/schema"
MANIFEST_PATH = SCHEMA_DIR / "app_schema_manifest.json"

SUPABASE_ROLE_PRELUDE = """
do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'service_role') then create role service_role; end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then create role authenticated; end if;
  if not exists (select 1 from pg_roles where rolname = 'anon') then create role anon; end if;
end $$;
""".strip()

APP_SCHEMA_STATE_SQL = """
select
  (select count(*) from information_schema.schemata where schema_name = any(%s)) as schema_count,
  (select count(*) from information_schema.tables where table_schema = any(%s) and table_type = 'BASE TABLE') as table_count,
  (select count(*) from information_schema.routines where specific_schema = any(%s) and routine_type = 'FUNCTION') as function_count
""".strip()


def local_supabase_role_grants_sql(schemas: list[str]) -> str:
    schema_list = ", ".join(schemas)
    return f"""
grant usage on schema {schema_list} to service_role;
grant all privileges on all tables in schema {schema_list} to service_role;
grant all privileges on all sequences in schema {schema_list} to service_role;
grant all privileges on all functions in schema {schema_list} to service_role;
""".strip()


def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError(f"schema manifest must be a JSON object: {path}")
    return data


def ordered_schema_files(schema_dir: Path = SCHEMA_DIR) -> list[Path]:
    manifest = load_manifest(schema_dir / "app_schema_manifest.json")
    baseline = manifest.get("baseline")
    patches = manifest.get("patches")
    if not isinstance(baseline, str) or not isinstance(patches, list) or not all(isinstance(item, str) for item in patches):
        raise RuntimeError("schema manifest must define string baseline and string patch list")
    files = [schema_dir / baseline, *(schema_dir / patch for patch in patches)]
    missing = [path for path in files if not path.is_file()]
    if missing:
        rel = ", ".join(path.relative_to(REPO_ROOT).as_posix() for path in missing)
        raise RuntimeError(f"schema manifest references missing SQL files: {rel}")
    return files


def app_schema_expectations(schema_dir: Path = SCHEMA_DIR) -> tuple[list[str], int, int]:
    manifest = load_manifest(schema_dir / "app_schema_manifest.json")
    schemas = manifest.get("app_owned_schemas")
    table_count = manifest.get("baseline_table_count")
    function_count = manifest.get("baseline_function_count")
    if (
        not isinstance(schemas, list)
        or not all(isinstance(item, str) and item for item in schemas)
        or not isinstance(table_count, int)
        or not isinstance(function_count, int)
    ):
        raise RuntimeError("schema manifest must define app_owned_schemas, baseline_table_count, and baseline_function_count")
    return schemas, table_count, function_count


def apply_schema(database_url: str, *, prepare_supabase_roles: bool = False, schema_dir: Path = SCHEMA_DIR) -> list[Path]:
    import psycopg

    files = ordered_schema_files(schema_dir)
    schemas, expected_tables, expected_functions = app_schema_expectations(schema_dir)
    if prepare_supabase_roles:
        with psycopg.connect(database_url, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(SUPABASE_ROLE_PRELUDE)

    with psycopg.connect(database_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(APP_SCHEMA_STATE_SQL, (schemas, schemas, schemas))
            row = cur.fetchone()
    schema_count, table_count, function_count = row
    if (schema_count, table_count, function_count) == (0, 0, 0):
        pass
    elif (schema_count, table_count, function_count) == (len(schemas), expected_tables, expected_functions):
        return []
    else:
        raise RuntimeError(
            "database already contains a partial or drifted app schema: "
            f"schemas={schema_count}/{len(schemas)}, tables={table_count}/{expected_tables}, "
            f"functions={function_count}/{expected_functions}"
        )

    for path in files:
        with psycopg.connect(database_url, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(path.read_text(encoding="utf-8"))
    if prepare_supabase_roles:
        with psycopg.connect(database_url, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(local_supabase_role_grants_sql(schemas))
    return files


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Apply the Mycel app schema baseline and manifest patches to a PostgreSQL database.")
    parser.add_argument(
        "--database-url",
        default=os.environ.get("LEON_POSTGRES_URL"),
        help="PostgreSQL URL. Defaults to LEON_POSTGRES_URL.",
    )
    parser.add_argument(
        "--prepare-supabase-roles",
        action="store_true",
        help="Create service_role, authenticated, and anon if missing. Use for plain local PostgreSQL, not managed Supabase.",
    )
    parser.add_argument("--print-files", action="store_true", help="Print the manifest apply order and exit without connecting.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        files = ordered_schema_files()
        if args.print_files:
            for path in files:
                print(path.relative_to(REPO_ROOT).as_posix())
            return 0
        if not args.database_url:
            raise RuntimeError("missing database URL: pass --database-url or set LEON_POSTGRES_URL")
        applied = apply_schema(args.database_url, prepare_supabase_roles=args.prepare_supabase_roles)
    except Exception as exc:
        print(f"App schema apply failed: {exc}", file=sys.stderr)
        return 1

    print(f"App schema apply passed: {len(applied)} SQL files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
