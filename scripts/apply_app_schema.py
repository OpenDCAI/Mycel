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


def apply_schema(database_url: str, *, prepare_supabase_roles: bool = False, schema_dir: Path = SCHEMA_DIR) -> list[Path]:
    import psycopg

    files = ordered_schema_files(schema_dir)
    if prepare_supabase_roles:
        with psycopg.connect(database_url, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(SUPABASE_ROLE_PRELUDE)

    for path in files:
        with psycopg.connect(database_url, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(path.read_text(encoding="utf-8"))
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
