import sqlite3

from backend.web import monitor


def _bootstrap_threads_monitor_db(db_path, count: int) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
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
    for idx in range(count):
        hour = idx // 60
        minute = idx % 60
        conn.execute(
            """
            INSERT INTO chat_sessions (
                chat_session_id, thread_id, lease_id, status, started_at, last_active_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                f"sess-{idx}",
                f"thread-{idx:03d}",
                None,
                "closed",
                f"2026-04-06T{hour:02d}:{minute:02d}:00",
                f"2026-04-06T{hour:02d}:{minute:02d}:30",
            ),
        )
    conn.commit()
    return conn


def test_list_running_eval_checkpoint_threads_returns_empty_when_eval_tables_absent(tmp_path, monkeypatch):
    db_path = tmp_path / "leon.db"
    sqlite3.connect(db_path).close()
    monkeypatch.setattr(monitor, "DB_PATH", db_path)

    assert monitor._list_running_eval_checkpoint_threads() == []


def test_list_threads_second_page_is_not_sliced_empty_after_sql_pagination(tmp_path, monkeypatch):
    db_path = tmp_path / "sandbox.db"
    conn = _bootstrap_threads_monitor_db(db_path, count=74)
    try:
        monkeypatch.setattr(monitor, "_list_running_eval_checkpoint_threads", lambda: [])
        monkeypatch.setattr(monitor, "load_thread_mode_map", lambda thread_ids: {})

        payload = monitor.list_threads(offset=50, limit=50, db=conn)
    finally:
        conn.close()

    assert payload["count"] == 24
    assert len(payload["items"]) == 24
    assert payload["items"][0]["thread_id"] == "thread-023"
    assert payload["items"][-1]["thread_id"] == "thread-000"
    assert payload["pagination"]["page"] == 2
    assert payload["pagination"]["has_prev"] is True
    assert payload["pagination"]["has_next"] is False
    assert payload["pagination"]["next_offset"] is None
