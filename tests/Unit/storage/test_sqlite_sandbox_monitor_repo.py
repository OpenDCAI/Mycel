from __future__ import annotations

import sqlite3
from pathlib import Path

from storage.providers.sqlite.sandbox_monitor_repo import SQLiteSandboxMonitorRepo


def _seed_sandbox_db(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE sandbox_leases (
                lease_id TEXT PRIMARY KEY,
                provider_name TEXT NOT NULL,
                recipe_id TEXT,
                recipe_json TEXT,
                desired_state TEXT,
                observed_state TEXT,
                current_instance_id TEXT,
                last_error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE abstract_terminals (
                terminal_id TEXT PRIMARY KEY,
                thread_id TEXT,
                lease_id TEXT,
                cwd TEXT,
                env_delta_json TEXT,
                state_version INTEGER,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO sandbox_leases (
                lease_id, provider_name, recipe_id, recipe_json, desired_state, observed_state,
                current_instance_id, last_error, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "lease-1",
                "daytona_selfhost",
                "daytona:default",
                None,
                "running",
                "running",
                None,
                None,
                "2026-04-07T10:00:00Z",
                "2026-04-07T10:01:00Z",
            ),
        )
        conn.execute(
            """
            INSERT INTO abstract_terminals (
                terminal_id, thread_id, lease_id, cwd, env_delta_json, state_version, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "term-1",
                "thread-1",
                "lease-1",
                "/home/daytona/app",
                "{}",
                1,
                "2026-04-07T10:00:30Z",
                "2026-04-07T10:01:30Z",
            ),
        )


def test_list_leases_with_threads_exposes_lease_created_at(tmp_path: Path) -> None:
    db_path = tmp_path / "sandbox.db"
    _seed_sandbox_db(db_path)

    repo = SQLiteSandboxMonitorRepo(db_path=db_path)
    try:
        rows = repo.list_leases_with_threads()
    finally:
        repo.close()

    assert rows == [
        {
            "lease_id": "lease-1",
            "provider_name": "daytona_selfhost",
            "recipe_id": "daytona:default",
            "recipe_json": None,
            "desired_state": "running",
            "observed_state": "running",
            "created_at": "2026-04-07T10:00:00Z",
            "updated_at": "2026-04-07T10:01:00Z",
            "thread_id": "thread-1",
            "cwd": "/home/daytona/app",
        }
    ]
