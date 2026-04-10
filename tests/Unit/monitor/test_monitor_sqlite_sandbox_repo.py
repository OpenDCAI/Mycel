import sqlite3

import pytest

from storage.providers.sqlite.sandbox_monitor_repo import SQLiteSandboxMonitorRepo
from storage.providers.supabase.sandbox_monitor_repo import SupabaseSandboxMonitorRepo
from tests.fakes.supabase import FakeSupabaseClient


class _BrokenSandboxInstancesClient(FakeSupabaseClient):
    def table(self, table_name: str):
        if table_name == "sandbox_instances":
            raise RuntimeError("sandbox_instances exploded")
        return super().table(table_name)


class _CountResponse:
    def __init__(self, count: int) -> None:
        self.data = []
        self.count = count


class _CountQuery:
    def __init__(self, count: int) -> None:
        self._count = count

    def select(self, _columns: str, **_kwargs):
        return self

    def limit(self, _value: int):
        return self

    def execute(self):
        return _CountResponse(self._count)


class _CountClient:
    def __init__(self, counts: dict[str, int]) -> None:
        self._counts = counts

    def table(self, table_name: str):
        return _CountQuery(self._counts[table_name])


class _BrokenCountClient(_CountClient):
    def table(self, table_name: str):
        if table_name == "sandbox_leases":
            raise RuntimeError("count exploded")
        return super().table(table_name)


def _bootstrap_monitor_db(db_path):
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE sandbox_leases (
                lease_id TEXT PRIMARY KEY,
                provider_name TEXT,
                recipe_id TEXT,
                recipe_json TEXT,
                desired_state TEXT,
                observed_state TEXT,
                current_instance_id TEXT,
                last_error TEXT,
                created_at TEXT,
                updated_at TEXT
            );

            CREATE TABLE abstract_terminals (
                terminal_id TEXT PRIMARY KEY,
                lease_id TEXT,
                thread_id TEXT,
                cwd TEXT,
                created_at TEXT
            );

            CREATE TABLE sandbox_instances (
                instance_id TEXT PRIMARY KEY,
                lease_id TEXT,
                provider_session_id TEXT
            );

            CREATE TABLE chat_sessions (
                chat_session_id TEXT PRIMARY KEY,
                thread_id TEXT,
                lease_id TEXT,
                status TEXT,
                started_at TEXT,
                last_active_at TEXT
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


def test_list_sessions_with_leases_keeps_raw_newest_terminal_truth(tmp_path):
    db_path = tmp_path / "sandbox.db"
    _bootstrap_monitor_db(db_path)

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO sandbox_leases (
                lease_id, provider_name, desired_state, observed_state, current_instance_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "lease-1",
                "daytona_selfhost",
                "paused",
                "paused",
                "instance-1",
                "2026-04-05T13:00:00",
                "2026-04-05T23:59:00",
            ),
        )
        conn.executemany(
            """
            INSERT INTO abstract_terminals (terminal_id, lease_id, thread_id, cwd, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                ("term-parent", "lease-1", "thread-parent", "/home/daytona/files/app", "2026-04-05T13:35:08"),
                ("term-subagent", "lease-1", "subagent-deadbeef", "/home/daytona/files/app", "2026-04-05T23:51:40"),
            ],
        )
        conn.executemany(
            """
            INSERT INTO chat_sessions (chat_session_id, thread_id, lease_id, status, started_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                ("sess-parent", "thread-parent", "lease-1", "closed", "2026-04-05T23:24:06"),
                ("sess-subagent", "subagent-deadbeef", "lease-1", "closed", "2026-04-05T23:51:42"),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    repo = SQLiteSandboxMonitorRepo(db_path=db_path)
    try:
        rows = repo.list_sessions_with_leases()
    finally:
        repo.close()

    assert len(rows) == 2
    assert {row["thread_id"] for row in rows} == {"thread-parent", "subagent-deadbeef"}
    assert all(row["lease_id"] == "lease-1" for row in rows)


def test_query_threads_accepts_optional_thread_filter(tmp_path):
    db_path = tmp_path / "sandbox.db"
    _bootstrap_monitor_db(db_path)

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO sandbox_leases (
                lease_id, provider_name, desired_state, observed_state, current_instance_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("lease-1", "local", "running", "running", "instance-1", "2026-04-05T10:00:00", "2026-04-05T10:00:00"),
        )
        conn.executemany(
            """
            INSERT INTO chat_sessions (chat_session_id, thread_id, lease_id, status, started_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                ("sess-1", "thread-1", "lease-1", "active", "2026-04-05T10:00:00"),
                ("sess-2", "thread-2", "lease-1", "active", "2026-04-05T10:05:00"),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    repo = SQLiteSandboxMonitorRepo(db_path=db_path)
    try:
        rows = repo.query_threads(thread_id="thread-2")
    finally:
        repo.close()

    assert [row["thread_id"] for row in rows] == ["thread-2"]


def test_supabase_query_threads_accepts_optional_thread_filter_matches_sqlite(tmp_path):
    db_path = tmp_path / "sandbox.db"
    _bootstrap_monitor_db(db_path)

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO sandbox_leases (
                lease_id, provider_name, desired_state, observed_state, current_instance_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("lease-1", "local", "running", "running", "instance-1", "2026-04-05T10:00:00", "2026-04-05T10:00:00"),
        )
        conn.executemany(
            """
            INSERT INTO chat_sessions (chat_session_id, thread_id, lease_id, status, started_at, last_active_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                ("sess-1", "thread-1", "lease-1", "active", "2026-04-05T10:00:00", "2026-04-05T10:01:00"),
                ("sess-2", "thread-2", "lease-1", "active", "2026-04-05T10:05:00", "2026-04-05T10:06:00"),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    sqlite_repo = SQLiteSandboxMonitorRepo(db_path=db_path)
    try:
        sqlite_rows = sqlite_repo.query_threads(thread_id="thread-2")
    finally:
        sqlite_repo.close()

    supabase_tables = {
        "sandbox_leases": [
            {
                "lease_id": "lease-1",
                "provider_name": "local",
                "desired_state": "running",
                "observed_state": "running",
                "current_instance_id": "instance-1",
            }
        ],
        "chat_sessions": [
            {
                "chat_session_id": "sess-1",
                "thread_id": "thread-1",
                "lease_id": "lease-1",
                "status": "active",
                "started_at": "2026-04-05T10:00:00",
                "last_active_at": "2026-04-05T10:01:00",
            },
            {
                "chat_session_id": "sess-2",
                "thread_id": "thread-2",
                "lease_id": "lease-1",
                "status": "active",
                "started_at": "2026-04-05T10:05:00",
                "last_active_at": "2026-04-05T10:06:00",
            },
        ],
    }
    supabase_repo = SupabaseSandboxMonitorRepo(FakeSupabaseClient(supabase_tables))

    supabase_rows = supabase_repo.query_threads(thread_id="thread-2")

    assert supabase_rows == sqlite_rows


def test_supabase_query_leases_uses_latest_terminal_binding_matches_sqlite(tmp_path):
    db_path = tmp_path / "sandbox.db"
    _bootstrap_monitor_db(db_path)

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO sandbox_leases (
                lease_id, provider_name, desired_state, observed_state, current_instance_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("lease-1", "daytona_selfhost", "paused", "paused", "instance-1", "2026-04-05T10:00:00", "2026-04-05T10:10:00"),
        )
        conn.executemany(
            """
            INSERT INTO abstract_terminals (terminal_id, lease_id, thread_id, cwd, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                ("term-old", "lease-1", "thread-old", "/workspace", "2026-04-05T10:01:00"),
                ("term-new", "lease-1", "thread-new", "/workspace", "2026-04-05T10:02:00"),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    sqlite_repo = SQLiteSandboxMonitorRepo(db_path=db_path)
    try:
        sqlite_rows = sqlite_repo.query_leases()
    finally:
        sqlite_repo.close()

    supabase_tables = {
        "sandbox_leases": [
            {
                "lease_id": "lease-1",
                "provider_name": "daytona_selfhost",
                "desired_state": "paused",
                "observed_state": "paused",
                "current_instance_id": "instance-1",
                "updated_at": "2026-04-05T10:10:00",
                "recipe_id": None,
                "recipe_json": None,
                "last_error": None,
            }
        ],
        "abstract_terminals": [
            {"terminal_id": "term-old", "lease_id": "lease-1", "thread_id": "thread-old", "created_at": "2026-04-05T10:01:00"},
            {"terminal_id": "term-new", "lease_id": "lease-1", "thread_id": "thread-new", "created_at": "2026-04-05T10:02:00"},
        ],
    }
    supabase_repo = SupabaseSandboxMonitorRepo(FakeSupabaseClient(supabase_tables))

    supabase_rows = supabase_repo.query_leases()

    assert supabase_rows == sqlite_rows


def test_supabase_query_lease_threads_matches_sqlite_latest_first(tmp_path):
    db_path = tmp_path / "sandbox.db"
    _bootstrap_monitor_db(db_path)

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO sandbox_leases (
                lease_id, provider_name, desired_state, observed_state, current_instance_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("lease-1", "daytona_selfhost", "paused", "paused", "instance-1", "2026-04-05T10:00:00", "2026-04-05T10:10:00"),
        )
        conn.executemany(
            """
            INSERT INTO abstract_terminals (terminal_id, lease_id, thread_id, cwd, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                ("term-old", "lease-1", "thread-old", "/workspace", "2026-04-05T10:01:00"),
                ("term-new", "lease-1", "thread-new", "/workspace", "2026-04-05T10:02:00"),
                ("term-dupe", "lease-1", "thread-new", "/workspace", "2026-04-05T10:03:00"),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    sqlite_repo = SQLiteSandboxMonitorRepo(db_path=db_path)
    try:
        sqlite_rows = sqlite_repo.query_lease_threads("lease-1")
    finally:
        sqlite_repo.close()

    supabase_tables = {
        "abstract_terminals": [
            {"terminal_id": "term-old", "lease_id": "lease-1", "thread_id": "thread-old", "created_at": "2026-04-05T10:01:00"},
            {"terminal_id": "term-new", "lease_id": "lease-1", "thread_id": "thread-new", "created_at": "2026-04-05T10:02:00"},
            {"terminal_id": "term-dupe", "lease_id": "lease-1", "thread_id": "thread-new", "created_at": "2026-04-05T10:03:00"},
        ]
    }
    supabase_repo = SupabaseSandboxMonitorRepo(FakeSupabaseClient(supabase_tables))

    supabase_rows = supabase_repo.query_lease_threads("lease-1")

    assert supabase_rows == sqlite_rows


def test_supabase_query_lease_instance_id_prefers_provider_session_id_matches_sqlite(tmp_path):
    db_path = tmp_path / "sandbox.db"
    _bootstrap_monitor_db(db_path)

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO sandbox_leases (
                lease_id, provider_name, desired_state, observed_state, current_instance_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("lease-1", "daytona_selfhost", "running", "detached", "instance-fallback", "2026-04-05T10:00:00", "2026-04-05T10:10:00"),
        )
        conn.execute(
            """
            INSERT INTO sandbox_instances (instance_id, lease_id, provider_session_id)
            VALUES (?, ?, ?)
            """,
            ("inst-row-1", "lease-1", "provider-session-1"),
        )
        conn.commit()
    finally:
        conn.close()

    sqlite_repo = SQLiteSandboxMonitorRepo(db_path=db_path)
    try:
        sqlite_value = sqlite_repo.query_lease_instance_id("lease-1")
    finally:
        sqlite_repo.close()

    supabase_tables = {
        "sandbox_leases": [
            {
                "lease_id": "lease-1",
                "provider_name": "daytona_selfhost",
                "desired_state": "running",
                "observed_state": "detached",
                "current_instance_id": "instance-fallback",
            }
        ],
        "sandbox_instances": [
            {"lease_id": "lease-1", "provider_session_id": "provider-session-1"},
        ],
    }
    supabase_repo = SupabaseSandboxMonitorRepo(FakeSupabaseClient(supabase_tables))

    supabase_value = supabase_repo.query_lease_instance_id("lease-1")

    assert supabase_value == sqlite_value == "provider-session-1"


def test_supabase_list_probe_targets_prefers_provider_session_id_matches_sqlite(tmp_path):
    db_path = tmp_path / "sandbox.db"
    _bootstrap_monitor_db(db_path)

    conn = sqlite3.connect(db_path)
    try:
        conn.executemany(
            """
            INSERT INTO sandbox_leases (
                lease_id, provider_name, desired_state, observed_state, current_instance_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "lease-running",
                    "daytona_selfhost",
                    "running",
                    "detached",
                    "instance-fallback",
                    "2026-04-05T10:00:00",
                    "2026-04-05T10:10:00",
                ),
                ("lease-paused", "local", "paused", "paused", "instance-local", "2026-04-05T10:00:01", "2026-04-05T10:11:00"),
                ("lease-stopped", "docker", "stopped", "stopped", "instance-stopped", "2026-04-05T10:00:02", "2026-04-05T10:12:00"),
            ],
        )
        conn.execute(
            """
            INSERT INTO sandbox_instances (instance_id, lease_id, provider_session_id)
            VALUES (?, ?, ?)
            """,
            ("inst-row-1", "lease-running", "provider-session-1"),
        )
        conn.commit()
    finally:
        conn.close()

    sqlite_repo = SQLiteSandboxMonitorRepo(db_path=db_path)
    try:
        sqlite_rows = sqlite_repo.list_probe_targets()
    finally:
        sqlite_repo.close()

    supabase_tables = {
        "sandbox_leases": [
            {
                "lease_id": "lease-running",
                "provider_name": "daytona_selfhost",
                "desired_state": "running",
                "observed_state": "detached",
                "current_instance_id": "instance-fallback",
                "updated_at": "2026-04-05T10:10:00",
            },
            {
                "lease_id": "lease-paused",
                "provider_name": "local",
                "desired_state": "paused",
                "observed_state": "paused",
                "current_instance_id": "instance-local",
                "updated_at": "2026-04-05T10:11:00",
            },
            {
                "lease_id": "lease-stopped",
                "provider_name": "docker",
                "desired_state": "stopped",
                "observed_state": "stopped",
                "current_instance_id": "instance-stopped",
                "updated_at": "2026-04-05T10:12:00",
            },
        ],
        "sandbox_instances": [
            {"lease_id": "lease-running", "provider_session_id": "provider-session-1"},
        ],
    }
    supabase_repo = SupabaseSandboxMonitorRepo(FakeSupabaseClient(supabase_tables))

    supabase_rows = supabase_repo.list_probe_targets()

    assert supabase_rows == sqlite_rows


def test_supabase_query_lease_instance_id_fails_loudly_when_instance_lookup_breaks() -> None:
    repo = SupabaseSandboxMonitorRepo(
        _BrokenSandboxInstancesClient(
            {
                "sandbox_leases": [
                    {
                        "lease_id": "lease-1",
                        "provider_name": "daytona_selfhost",
                        "desired_state": "running",
                        "observed_state": "detached",
                        "current_instance_id": "instance-fallback",
                    }
                ]
            }
        )
    )

    with pytest.raises(RuntimeError, match="sandbox_instances exploded"):
        repo.query_lease_instance_id("lease-1")


def test_supabase_list_probe_targets_fails_loudly_when_instance_lookup_breaks() -> None:
    repo = SupabaseSandboxMonitorRepo(
        _BrokenSandboxInstancesClient(
            {
                "sandbox_leases": [
                    {
                        "lease_id": "lease-1",
                        "provider_name": "daytona_selfhost",
                        "desired_state": "running",
                        "observed_state": "detached",
                        "current_instance_id": "instance-fallback",
                        "updated_at": "2026-04-05T10:10:00",
                    }
                ]
            }
        )
    )

    with pytest.raises(RuntimeError, match="sandbox_instances exploded"):
        repo.list_probe_targets()


def test_supabase_count_rows_returns_exact_counts() -> None:
    repo = SupabaseSandboxMonitorRepo(
        _CountClient(
            {
                "chat_sessions": 3,
                "sandbox_leases": 5,
                "provider_events": 7,
            }
        )
    )

    assert repo.count_rows(["chat_sessions", "sandbox_leases", "provider_events"]) == {
        "chat_sessions": 3,
        "sandbox_leases": 5,
        "provider_events": 7,
    }


def test_supabase_count_rows_fails_loudly_when_count_query_breaks() -> None:
    repo = SupabaseSandboxMonitorRepo(_BrokenCountClient({"chat_sessions": 3, "sandbox_leases": 5}))

    with pytest.raises(RuntimeError, match="count exploded"):
        repo.count_rows(["chat_sessions", "sandbox_leases"])


def test_supabase_list_sessions_with_leases_matches_sqlite_terminal_and_recent_session_fallback(tmp_path):
    db_path = tmp_path / "sandbox.db"
    _bootstrap_monitor_db(db_path)

    sqlite_conn = sqlite3.connect(db_path)
    try:
        sqlite_conn.executemany(
            """
            INSERT INTO sandbox_leases (
                lease_id, provider_name, desired_state, observed_state, current_instance_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("lease-active", "local", "running", "running", "instance-a", "2026-04-05T10:00:00", "2026-04-05T10:00:00"),
                ("lease-terminal", "daytona_selfhost", "paused", "paused", "instance-b", "2026-04-05T11:00:00", "2026-04-05T11:00:00"),
                ("lease-recent", "docker", "paused", "paused", "instance-c", "2026-04-05T12:00:00", "2026-04-05T12:00:00"),
            ],
        )
        sqlite_conn.executemany(
            """
            INSERT INTO abstract_terminals (terminal_id, lease_id, thread_id, cwd, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                ("term-parent", "lease-terminal", "thread-parent", "/workspace", "2026-04-05T11:05:00"),
                ("term-subagent", "lease-terminal", "subagent-deadbeef", "/workspace", "2026-04-05T11:06:00"),
            ],
        )
        sqlite_conn.executemany(
            """
            INSERT INTO chat_sessions (chat_session_id, thread_id, lease_id, status, started_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                ("sess-active", "thread-active", "lease-active", "active", "2026-04-05T10:01:00"),
                ("sess-recent-a", "thread-old", "lease-recent", "closed", "2026-04-05T12:01:00"),
                ("sess-recent-b", "thread-new", "lease-recent", "closed", "2026-04-05T12:02:00"),
            ],
        )
        sqlite_conn.commit()
    finally:
        sqlite_conn.close()

    sqlite_repo = SQLiteSandboxMonitorRepo(db_path=db_path)
    try:
        sqlite_rows = sqlite_repo.list_sessions_with_leases()
    finally:
        sqlite_repo.close()

    supabase_tables = {
        "sandbox_leases": [
            {
                "lease_id": "lease-active",
                "provider_name": "local",
                "desired_state": "running",
                "observed_state": "running",
                "current_instance_id": "instance-a",
                "created_at": "2026-04-05T10:00:00",
                "updated_at": "2026-04-05T10:00:00",
            },
            {
                "lease_id": "lease-terminal",
                "provider_name": "daytona_selfhost",
                "desired_state": "paused",
                "observed_state": "paused",
                "current_instance_id": "instance-b",
                "created_at": "2026-04-05T11:00:00",
                "updated_at": "2026-04-05T11:00:00",
            },
            {
                "lease_id": "lease-recent",
                "provider_name": "docker",
                "desired_state": "paused",
                "observed_state": "paused",
                "current_instance_id": "instance-c",
                "created_at": "2026-04-05T12:00:00",
                "updated_at": "2026-04-05T12:00:00",
            },
        ],
        "abstract_terminals": [
            {"terminal_id": "term-parent", "lease_id": "lease-terminal", "thread_id": "thread-parent", "created_at": "2026-04-05T11:05:00"},
            {
                "terminal_id": "term-subagent",
                "lease_id": "lease-terminal",
                "thread_id": "subagent-deadbeef",
                "created_at": "2026-04-05T11:06:00",
            },
        ],
        "chat_sessions": [
            {
                "chat_session_id": "sess-active",
                "thread_id": "thread-active",
                "lease_id": "lease-active",
                "status": "active",
                "started_at": "2026-04-05T10:01:00",
            },
            {
                "chat_session_id": "sess-recent-a",
                "thread_id": "thread-old",
                "lease_id": "lease-recent",
                "status": "closed",
                "started_at": "2026-04-05T12:01:00",
            },
            {
                "chat_session_id": "sess-recent-b",
                "thread_id": "thread-new",
                "lease_id": "lease-recent",
                "status": "closed",
                "started_at": "2026-04-05T12:02:00",
            },
        ],
    }
    supabase_repo = SupabaseSandboxMonitorRepo(FakeSupabaseClient(supabase_tables))

    supabase_rows = supabase_repo.list_sessions_with_leases()

    assert supabase_rows == sqlite_rows
