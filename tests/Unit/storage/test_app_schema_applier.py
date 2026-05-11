from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APPLIER_PATH = ROOT / "scripts/apply_app_schema.py"


def _load_applier():
    spec = importlib.util.spec_from_file_location("apply_app_schema", APPLIER_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_applier_uses_manifest_order() -> None:
    applier = _load_applier()

    files = [path.relative_to(ROOT).as_posix() for path in applier.ordered_schema_files(ROOT / "storage/schema")]

    assert files[0] == "storage/schema/app_schema.sql"
    assert files[1:] == [
        "storage/schema/agent_config_resolved_config_hardcut.sql",
        "storage/schema/chat_join_requests.sql",
        "storage/schema/chat_message_delivery_scope.sql",
        "storage/schema/chat_workflow_state_and_tasks.sql",
        "storage/schema/external_user_creator.sql",
        "storage/schema/relationship_pair_constraint.sql",
        "storage/schema/relationship_request_message.sql",
        "storage/schema/sandbox_control_plane_supabase.sql",
        "storage/schema/user_is_guest.sql",
    ]


def test_chat_workflow_state_version_patch_updates_existing_tables() -> None:
    sql = (ROOT / "storage/schema/chat_workflow_state_and_tasks.sql").read_text(encoding="utf-8")

    assert "add column if not exists state_version" in sql


def test_applier_print_files_is_connection_free() -> None:
    result = subprocess.run(
        [sys.executable, str(APPLIER_PATH), "--print-files"],
        cwd=ROOT,
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0
    assert result.stdout.splitlines()[0] == "storage/schema/app_schema.sql"
    assert result.stderr == ""


def test_applier_fails_loudly_without_database_url() -> None:
    env = os.environ.copy()
    env.pop("LEON_POSTGRES_URL", None)
    result = subprocess.run(
        [sys.executable, str(APPLIER_PATH)],
        cwd=ROOT,
        check=False,
        text=True,
        capture_output=True,
        env=env,
    )

    assert result.returncode == 1
    assert "missing database URL" in result.stderr


def test_supabase_role_prelude_is_explicit() -> None:
    applier = _load_applier()

    assert "create role service_role" in applier.SUPABASE_ROLE_PRELUDE
    assert "create role authenticated" in applier.SUPABASE_ROLE_PRELUDE
    assert "create role anon" in applier.SUPABASE_ROLE_PRELUDE


def test_local_supabase_role_grants_cover_all_app_owned_schemas() -> None:
    applier = _load_applier()

    sql = applier.local_supabase_role_grants_sql(["identity", "chat"])

    assert "grant usage on schema identity, chat to service_role" in sql
    assert "grant all privileges on all tables in schema identity, chat to service_role" in sql
    assert "grant all privileges on all sequences in schema identity, chat to service_role" in sql
    assert "grant all privileges on all functions in schema identity, chat to service_role" in sql


def test_applier_isolates_session_state_between_schema_files(tmp_path, monkeypatch) -> None:
    applier = _load_applier()
    schema_dir = tmp_path / "schema"
    schema_dir.mkdir()
    (schema_dir / "app_schema_manifest.json").write_text(
        (
            '{"baseline": "baseline.sql", "patches": ["patch.sql"], '
            '"app_owned_schemas": ["identity"], "baseline_table_count": 0, "baseline_function_count": 0}'
        ),
        encoding="utf-8",
    )
    (schema_dir / "baseline.sql").write_text("select set_config('search_path', '', false);", encoding="utf-8")
    (schema_dir / "patch.sql").write_text("create extension if not exists pgcrypto;", encoding="utf-8")
    executed: list[list[str]] = []
    fetch_results = [(0, 0, 0)]

    class Cursor:
        def __init__(self, statements: list[str]) -> None:
            self._statements = statements

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            return None

        def execute(self, statement: str, params=None) -> None:
            self._statements.append(statement)

        def fetchone(self):
            return fetch_results.pop(0)

    class Connection:
        def __init__(self) -> None:
            self.statements: list[str] = []
            executed.append(self.statements)

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            return None

        def cursor(self) -> Cursor:
            return Cursor(self.statements)

    fake_psycopg = types.SimpleNamespace(connect=lambda *args, **kwargs: Connection())
    monkeypatch.setitem(sys.modules, "psycopg", fake_psycopg)

    applier.apply_schema("postgresql://example", prepare_supabase_roles=True, schema_dir=schema_dir)

    assert executed == [
        [applier.SUPABASE_ROLE_PRELUDE],
        [applier.APP_SCHEMA_STATE_SQL],
        ["select set_config('search_path', '', false);"],
        ["create extension if not exists pgcrypto;"],
        [applier.local_supabase_role_grants_sql(["identity"])],
    ]


def test_applier_skips_database_that_already_matches_manifest(tmp_path, monkeypatch) -> None:
    applier = _load_applier()
    schema_dir = tmp_path / "schema"
    schema_dir.mkdir()
    (schema_dir / "app_schema_manifest.json").write_text(
        (
            '{"baseline": "baseline.sql", "patches": ["patch.sql"], '
            '"app_owned_schemas": ["identity"], "baseline_table_count": 2, "baseline_function_count": 1}'
        ),
        encoding="utf-8",
    )
    (schema_dir / "baseline.sql").write_text("create schema identity;", encoding="utf-8")
    (schema_dir / "patch.sql").write_text("alter table identity.users add column name text;", encoding="utf-8")
    executed: list[list[str]] = []

    class Cursor:
        def __init__(self, statements: list[str]) -> None:
            self._statements = statements

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            return None

        def execute(self, statement: str, params=None) -> None:
            self._statements.append(statement)

        def fetchone(self):
            return (1, 2, 1)

    class Connection:
        def __init__(self) -> None:
            self.statements: list[str] = []
            executed.append(self.statements)

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            return None

        def cursor(self) -> Cursor:
            return Cursor(self.statements)

    fake_psycopg = types.SimpleNamespace(connect=lambda *args, **kwargs: Connection())
    monkeypatch.setitem(sys.modules, "psycopg", fake_psycopg)

    applied = applier.apply_schema("postgresql://example", schema_dir=schema_dir)

    assert applied == []
    assert len(executed) == 1
    assert "information_schema.schemata" in executed[0][0]


def test_applier_fails_loudly_on_partial_app_schema(tmp_path, monkeypatch) -> None:
    applier = _load_applier()
    schema_dir = tmp_path / "schema"
    schema_dir.mkdir()
    (schema_dir / "app_schema_manifest.json").write_text(
        (
            '{"baseline": "baseline.sql", "patches": [], '
            '"app_owned_schemas": ["identity", "chat"], "baseline_table_count": 2, "baseline_function_count": 0}'
        ),
        encoding="utf-8",
    )
    (schema_dir / "baseline.sql").write_text("create schema identity; create schema chat;", encoding="utf-8")

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            return None

        def execute(self, statement: str, params=None) -> None:
            return None

        def fetchone(self):
            return (1, 1, 0)

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            return None

        def cursor(self) -> Cursor:
            return Cursor()

    fake_psycopg = types.SimpleNamespace(connect=lambda *args, **kwargs: Connection())
    monkeypatch.setitem(sys.modules, "psycopg", fake_psycopg)

    try:
        applier.apply_schema("postgresql://example", schema_dir=schema_dir)
    except RuntimeError as exc:
        assert "already contains a partial or drifted app schema" in str(exc)
    else:
        raise AssertionError("expected partial schema to fail loudly")
