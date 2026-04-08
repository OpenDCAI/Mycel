from backend.web.services import monitor_service


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


def test_get_lease_falls_back_to_historical_session_rows(monkeypatch):
    class FakeRepo:
        def query_lease(self, lease_id):
            return None

        def query_lease_threads(self, lease_id):
            return []

        def query_lease_events(self, lease_id):
            return []

        def query_lease_sessions(self, lease_id):
            return [
                {
                    "chat_session_id": "sess-old",
                    "thread_id": "thread-historical",
                    "status": "closed",
                    "started_at": "2026-04-06T10:00:00",
                    "ended_at": "2026-04-06T10:05:00",
                    "close_reason": "expired",
                    "lease_id": lease_id,
                    "provider_name": None,
                    "desired_state": None,
                    "observed_state": None,
                    "current_instance_id": None,
                    "last_error": None,
                }
            ]

        def close(self):
            return None

    monkeypatch.setattr(monitor_service, "make_sandbox_monitor_repo", lambda: FakeRepo())

    payload = monitor_service.get_lease("lease-historical")

    assert payload["lease_id"] == "lease-historical"
    assert payload["info"]["provider"] == "unknown"
    assert payload["state"]["text"] == "destroyed"
    assert payload["related_threads"]["items"] == [{"thread_id": "thread-historical", "thread_url": "/thread/thread-historical"}]


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

    assert payload["status"] == "provisional"
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

    assert payload["status"] == "running"
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

    assert payload["status"] == "completed_with_errors"
    assert payload["kind"] == "completed_with_errors"
    assert payload["tone"] == "warning"
    assert "completed with recorded errors" in payload["headline"]
    assert payload["artifact_summary"] == {
        "present": 4,
        "missing": 2,
        "total": 6,
    }


def test_monitor_evaluation_truth_defaults_to_explicit_unavailable_surface():
    payload = monitor_service.get_monitor_evaluation_truth()

    assert payload["status"] == "unavailable"
    assert payload["kind"] == "unavailable"
    assert payload["tone"] == "warning"
    assert payload["headline"] == "Evaluation operator truth is not wired in this runtime yet."
    assert payload["artifact_summary"] == {
        "present": 0,
        "missing": 0,
        "total": 0,
    }
    assert payload["raw_notes"] is None


def test_monitor_evaluation_dashboard_summary_reduces_operator_truth():
    summary = monitor_service.build_monitor_evaluation_dashboard_summary(
        {
            "status": "running",
            "kind": "running_active",
            "tone": "default",
            "headline": "Evaluation is actively running.",
            "summary": "Long form summary that should not leak into dashboard shape.",
            "facts": [],
            "artifacts": [],
            "artifact_summary": {"present": 2, "missing": 1, "total": 3},
            "next_steps": [],
            "raw_notes": "runner=direct rc=0",
        }
    )

    assert summary == {
        "evaluations_running": 1,
        "latest_evaluation": {
            "status": "running",
            "kind": "running_active",
            "tone": "default",
            "headline": "Evaluation is actively running.",
        },
    }


def test_cleanup_resource_leases_deletes_allowed_detached_residue(monkeypatch):
    rows = [
        {
            "lease_id": "lease-stale",
            "provider_name": "local",
            "desired_state": "running",
            "observed_state": "detached",
            "current_instance_id": None,
            "last_error": None,
            "updated_at": "2026-04-05T00:00:00",
            "thread_id": "subagent-1234",
        }
    ]

    class FakeMonitorRepo:
        def query_leases(self):
            return list(rows)

        def query_lease_sessions(self, lease_id):
            assert lease_id == "lease-stale"
            return [{"chat_session_id": "sess-old", "status": "closed"}]

        def close(self):
            return None

    class FakeLeaseRepo:
        def __init__(self):
            self.deleted = []

        def delete(self, lease_id):
            self.deleted.append(lease_id)
            rows[:] = [row for row in rows if row["lease_id"] != lease_id]

        def close(self):
            return None

    class FakeChatSessionRepo:
        def lease_has_running_command(self, lease_id):
            assert lease_id == "lease-stale"
            return False

        def close(self):
            return None

    lease_repo = FakeLeaseRepo()
    monkeypatch.setattr(monitor_service, "make_sandbox_monitor_repo", lambda: FakeMonitorRepo())
    monkeypatch.setattr(monitor_service, "make_lease_repo", lambda: lease_repo)
    monkeypatch.setattr(monitor_service, "make_chat_session_repo", lambda: FakeChatSessionRepo())
    monkeypatch.setattr(monitor_service, "init_providers_and_managers", lambda: ({}, {}))
    monkeypatch.setattr(monitor_service, "_hours_since", lambda _: 24.0)

    payload = monitor_service.cleanup_resource_leases(
        action="cleanup_residue",
        lease_ids=["lease-stale"],
        expected_category="detached_residue",
    )

    assert lease_repo.deleted == ["lease-stale"]
    assert payload["attempted"] == ["lease-stale"]
    assert payload["cleaned"] == [{"lease_id": "lease-stale", "category": "detached_residue"}]
    assert payload["skipped"] == []
    assert payload["errors"] == []
    assert payload["refreshed_summary"]["detached_residue"] == 0


def test_cleanup_resource_leases_reports_category_mismatch_without_deleting(monkeypatch):
    rows = [
        {
            "lease_id": "lease-live",
            "provider_name": "local",
            "desired_state": "running",
            "observed_state": "detached",
            "current_instance_id": "inst-live",
            "last_error": None,
            "updated_at": "2026-04-06T00:00:00",
            "thread_id": "thread-1",
        }
    ]

    class FakeMonitorRepo:
        def query_leases(self):
            return list(rows)

        def query_lease_sessions(self, lease_id):
            assert lease_id == "lease-live"
            return [{"chat_session_id": "sess-live", "status": "active"}]

        def close(self):
            return None

    class FakeLeaseRepo:
        def __init__(self):
            self.deleted = []

        def delete(self, lease_id):
            self.deleted.append(lease_id)

        def close(self):
            return None

    class FakeChatSessionRepo:
        def lease_has_running_command(self, lease_id):
            assert lease_id == "lease-live"
            return True

        def close(self):
            return None

    lease_repo = FakeLeaseRepo()
    monkeypatch.setattr(monitor_service, "make_sandbox_monitor_repo", lambda: FakeMonitorRepo())
    monkeypatch.setattr(monitor_service, "make_lease_repo", lambda: lease_repo)
    monkeypatch.setattr(monitor_service, "make_chat_session_repo", lambda: FakeChatSessionRepo())
    monkeypatch.setattr(monitor_service, "init_providers_and_managers", lambda: ({}, {}))
    monkeypatch.setattr(monitor_service, "_hours_since", lambda _: 0.5)

    payload = monitor_service.cleanup_resource_leases(
        action="cleanup_residue",
        lease_ids=["lease-live"],
        expected_category="detached_residue",
    )

    assert lease_repo.deleted == []
    assert payload["attempted"] == ["lease-live"]
    assert payload["cleaned"] == []
    assert payload["skipped"] == ["lease-live"]
    assert payload["errors"] == [
        {
            "lease_id": "lease-live",
            "reason": "category_mismatch",
            "expected_category": "detached_residue",
            "actual_category": "active_drift",
        }
    ]


def test_runtime_health_snapshot_reports_supabase_storage_contract(monkeypatch):
    class FakeRepo:
        def count_rows(self, table_names):
            return {name: idx + 1 for idx, name in enumerate(table_names)}

        def close(self):
            return None

    monkeypatch.setenv("LEON_STORAGE_STRATEGY", "supabase")
    monkeypatch.setenv("LEON_DB_SCHEMA", "staging")
    monkeypatch.setattr(monitor_service, "make_sandbox_monitor_repo", lambda: FakeRepo())
    monkeypatch.setattr(monitor_service, "init_providers_and_managers", lambda: ({}, {}))
    monkeypatch.setattr(monitor_service, "load_all_sessions", lambda _managers: [])

    payload = monitor_service.runtime_health_snapshot()

    assert payload["db"] == {
        "strategy": "supabase",
        "schema": "staging",
        "counts": {
            "chat_sessions": 1,
            "sandbox_leases": 2,
            "lease_events": 3,
        },
    }
    assert payload["sessions"] == {"total": 0, "providers": {}}
