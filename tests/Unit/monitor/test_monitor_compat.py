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
    monkeypatch.setattr(
        monitor_service,
        "_hours_since",
        lambda iso_timestamp: {
            "2026-04-06T00:10:00": 0.5,
            "2026-04-06T00:11:00": 0.5,
            "2026-04-06T00:12:00": 10.0,
            "2026-04-06T00:13:00": 10.0,
        }.get(iso_timestamp),
    )

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
    assert payload["triage"]["summary"] == {
        "total": 4,
        "active_drift": 1,
        "detached_residue": 0,
        "orphan_cleanup": 2,
        "healthy_capacity": 1,
    }
    assert [group["key"] for group in payload["triage"]["groups"]] == [
        "active_drift",
        "detached_residue",
        "orphan_cleanup",
        "healthy_capacity",
    ]
    by_id = {item["lease_id"]: item for item in payload["items"]}
    assert by_id["lease-healthy"]["semantics"]["category"] == "healthy"
    assert by_id["lease-healthy"]["triage"]["category"] == "healthy_capacity"
    assert by_id["lease-diverged"]["semantics"]["category"] == "diverged"
    assert by_id["lease-diverged"]["triage"]["category"] == "active_drift"
    assert by_id["lease-orphan-diverged"]["semantics"]["category"] == "orphan_diverged"
    assert by_id["lease-orphan-diverged"]["triage"]["category"] == "orphan_cleanup"
    assert by_id["lease-orphan"]["semantics"]["category"] == "orphan"
    assert by_id["lease-orphan"]["triage"]["category"] == "orphan_cleanup"


def test_list_leases_marks_old_detached_running_rows_as_detached_residue(monkeypatch):
    class FakeRepo:
        def query_leases(self):
            return [
                {
                    "lease_id": "lease-stale",
                    "provider_name": "local",
                    "desired_state": "running",
                    "observed_state": "detached",
                    "current_instance_id": "inst-9",
                    "last_error": None,
                    "updated_at": "2026-04-05T00:00:00",
                    "thread_id": "subagent-1234",
                }
            ]

        def close(self):
            return None

    monkeypatch.setattr(monitor_service, "make_sandbox_monitor_repo", lambda: FakeRepo())
    monkeypatch.setattr(monitor_service, "_hours_since", lambda _: 24.0)

    payload = monitor_service.list_leases()

    item = payload["items"][0]
    assert item["semantics"]["category"] == "diverged"
    assert item["triage"]["category"] == "detached_residue"
    assert payload["triage"]["summary"]["detached_residue"] == 1


def test_build_evaluation_operator_surface_flags_runner_exit_before_threads_materialize():
    payload = monitor_service.build_evaluation_operator_surface(
        status="provisional",
        notes=("runner=direct rc=1 sandbox=local run_dir=/tmp/eval stdout_log=/tmp/eval/out.log stderr_log=/tmp/eval/err.log"),
        score={
            "score_gate": "provisional",
            "publishable": False,
            "run_dir": "/tmp/eval",
            "manifest_path": "/tmp/eval/run_manifest.json",
            "eval_summary_path": None,
            "trace_summaries_path": None,
            "scored": False,
        },
        threads_total=0,
        threads_running=0,
        threads_done=0,
    )

    assert payload["kind"] == "bootstrap_failure"
    assert payload["tone"] == "danger"
    assert payload["headline"] == "Runner exited before evaluation threads materialized."
    assert "bootstrap failure" in payload["summary"]
    assert payload["facts"][-2:] == [
        {"label": "Runner", "value": "direct"},
        {"label": "Exit code", "value": "1"},
    ]
    artifact_labels = {item["label"] for item in payload["artifacts"]}
    assert artifact_labels == {
        "Run directory",
        "Run manifest",
        "STDOUT log",
        "STDERR log",
        "Eval summary",
        "Trace summaries",
    }
    assert payload["artifact_summary"] == {
        "present": 4,
        "missing": 2,
        "total": 6,
    }
    assert payload["artifacts"][0]["status"] == "present"
    assert payload["artifacts"][-1]["status"] == "missing"


def test_build_evaluation_operator_surface_marks_running_waiting_for_threads():
    payload = monitor_service.build_evaluation_operator_surface(
        status="running",
        notes="runner=direct rc=0",
        score={
            "score_gate": "provisional",
            "publishable": False,
            "run_dir": "/tmp/eval",
            "manifest_path": "/tmp/eval/run_manifest.json",
            "eval_summary_path": None,
            "trace_summaries_path": None,
            "scored": False,
        },
        threads_total=0,
        threads_running=2,
        threads_done=0,
    )

    assert payload["kind"] == "running_waiting_for_threads"
    assert payload["tone"] == "default"
    assert "actively running" in payload["headline"]
    assert payload["artifact_summary"]["present"] == 2


def test_build_evaluation_operator_surface_marks_completed_with_errors():
    payload = monitor_service.build_evaluation_operator_surface(
        status="completed_with_errors",
        notes="runner=direct rc=0",
        score={
            "score_gate": "final",
            "publishable": True,
            "run_dir": "/tmp/eval",
            "manifest_path": "/tmp/eval/run_manifest.json",
            "eval_summary_path": "/tmp/eval/eval_summary.json",
            "trace_summaries_path": "/tmp/eval/trace_summaries.jsonl",
            "scored": True,
            "error_instances": 2,
        },
        threads_total=10,
        threads_running=0,
        threads_done=10,
    )

    assert payload["kind"] == "completed_with_errors"
    assert payload["tone"] == "warning"
    assert "completed with recorded errors" in payload["headline"]
    assert payload["artifact_summary"] == {
        "present": 4,
        "missing": 2,
        "total": 6,
    }
