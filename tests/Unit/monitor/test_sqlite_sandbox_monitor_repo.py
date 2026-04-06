import sqlite3

from storage.providers.sqlite.sandbox_monitor_repo import SQLiteSandboxMonitorRepo


def _bootstrap_monitor_db(db_path):
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE sandbox_leases (
                lease_id TEXT PRIMARY KEY,
                provider_name TEXT,
                desired_state TEXT,
                observed_state TEXT,
                current_instance_id TEXT,
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

            CREATE TABLE chat_sessions (
                chat_session_id TEXT PRIMARY KEY,
                thread_id TEXT,
                lease_id TEXT,
                status TEXT,
                started_at TEXT
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
