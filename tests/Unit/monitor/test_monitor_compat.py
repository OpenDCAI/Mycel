import sqlite3

from backend.web import monitor
from backend.web.services import monitor_service


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


def test_list_leases_exposes_semantic_groups_and_summary(monkeypatch):
    class FakeRepo:
        def query_leases(self):
            return [
                {
                    "lease_id": "lease-healthy",
                    "provider_name": "local",
                    "desired_state": "running",
                    "observed_state": "running",
                    "current_instance_id": "inst-1",
                    "last_error": None,
                    "updated_at": "2026-04-06T00:10:00",
                    "thread_id": "thread-1",
                },
                {
                    "lease_id": "lease-diverged",
                    "provider_name": "local",
                    "desired_state": "running",
                    "observed_state": "detached",
                    "current_instance_id": "inst-2",
                    "last_error": "drift",
                    "updated_at": "2026-04-06T00:11:00",
                    "thread_id": "thread-2",
                },
                {
                    "lease_id": "lease-orphan-diverged",
                    "provider_name": "local",
                    "desired_state": "running",
                    "observed_state": "detached",
                    "current_instance_id": "inst-3",
                    "last_error": None,
                    "updated_at": "2026-04-06T00:12:00",
                    "thread_id": None,
                },
                {
                    "lease_id": "lease-orphan",
                    "provider_name": "local",
                    "desired_state": "stopped",
                    "observed_state": "stopped",
                    "current_instance_id": "inst-4",
                    "last_error": None,
                    "updated_at": "2026-04-06T00:13:00",
                    "thread_id": None,
                },
            ]

        def close(self):
            return None

    monkeypatch.setattr(monitor_service, "make_sandbox_monitor_repo", lambda: FakeRepo())

    payload = monitor_service.list_leases()

    assert payload["summary"] == {
        "total": 4,
        "healthy": 1,
        "diverged": 1,
        "orphan": 1,
        "orphan_diverged": 1,
    }
    assert [group["key"] for group in payload["groups"]] == [
        "orphan_diverged",
        "diverged",
        "orphan",
        "healthy",
    ]
    by_id = {item["lease_id"]: item for item in payload["items"]}
    assert by_id["lease-healthy"]["semantics"]["category"] == "healthy"
    assert by_id["lease-diverged"]["semantics"]["category"] == "diverged"
    assert by_id["lease-orphan-diverged"]["semantics"]["category"] == "orphan_diverged"
    assert by_id["lease-orphan"]["semantics"]["category"] == "orphan"
