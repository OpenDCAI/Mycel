import pytest

from backend.monitor.infrastructure.persistence.operation_repo import InMemoryMonitorOperationRepo
from storage.providers.supabase.monitor_operation_repo import SupabaseMonitorOperationRepo
from tests.fakes.supabase import FakeSupabaseClient


def _operation(**overrides):
    payload = {
        "operation_id": "op-1",
        "kind": "sandbox_cleanup",
        "target_type": "sandbox",
        "target_id": "sandbox-1",
        "status": "pending",
        "requested_at": "2026-04-19T00:00:00Z",
        "updated_at": "2026-04-19T00:00:00Z",
        "summary": "Cleanup queued",
        "reason": "Sandbox is detached residue and can enter managed cleanup.",
        "target": {"target_type": "sandbox", "target_id": "sandbox-1"},
        "result_truth": {},
        "events": [{"at": "2026-04-19T00:00:00Z", "status": "pending", "message": "Cleanup queued"}],
    }
    payload.update(overrides)
    return payload


def test_supabase_monitor_operation_repo_uses_observability_schema_table() -> None:
    tables: dict[str, list[dict]] = {"observability.monitor_operations": []}
    repo = SupabaseMonitorOperationRepo(client=FakeSupabaseClient(tables=tables))

    created = repo.create(_operation())
    repo.save(_operation(status="succeeded", updated_at="2026-04-19T00:01:00Z", summary="Cleanup completed."))

    listed = repo.list_for_target("sandbox", "sandbox-1")
    loaded = repo.get("op-1")
    cleared = repo.clear()

    assert created["operation_id"] == "op-1"
    assert listed == [loaded]
    assert loaded is not None
    assert loaded["status"] == "succeeded"
    assert loaded["summary"] == "Cleanup completed."
    assert cleared == 1
    assert tables["observability.monitor_operations"] == []
    assert "monitor_operations" not in tables


@pytest.mark.parametrize(
    ("repo_factory"),
    [
        lambda: InMemoryMonitorOperationRepo(),
        lambda: SupabaseMonitorOperationRepo(client=FakeSupabaseClient(tables={"observability.monitor_operations": []})),
    ],
)
def test_monitor_operation_repo_contract_uses_upsert_and_requested_at_order(repo_factory) -> None:
    repo = repo_factory()

    repo.save(_operation(operation_id="op-older", requested_at="2026-04-19T00:00:00Z", updated_at="2026-04-19T00:00:00Z"))
    repo.save(_operation(operation_id="op-newer", requested_at="2026-04-19T00:01:00Z", updated_at="2026-04-19T00:01:00Z"))
    repo.create(
        _operation(
            operation_id="op-newer", summary="Updated by create", requested_at="2026-04-19T00:01:00Z", updated_at="2026-04-19T00:02:00Z"
        )
    )

    listed = repo.list_for_target("sandbox", "sandbox-1")
    loaded = repo.get("op-newer")
    cleared = repo.clear()

    assert [item["operation_id"] for item in listed] == ["op-newer", "op-older"]
    assert loaded is not None
    assert loaded["summary"] == "Updated by create"
    assert cleared == 2
