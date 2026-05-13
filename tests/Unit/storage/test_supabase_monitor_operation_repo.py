import pytest

from backend.monitor.infrastructure.persistence.operation_repo import InMemoryMonitorOperationRepo
from storage.providers.supabase.monitor_operation_repo import SupabaseMonitorOperationRepo
from tests.fakes.supabase import FakeSupabaseClient


class _FakeTable:
    def __init__(self) -> None:
        self.rows = []
        self.error: Exception | None = None

    def upsert(self, _payload, **_kwargs):
        return self

    def select(self, _cols):
        return self

    def eq(self, _column, _value):
        return self

    def neq(self, _column, _value):
        return self

    def order(self, _column, desc: bool = False):
        return self

    def delete(self):
        return self

    def execute(self):
        if self.error is not None:
            raise self.error
        return type("Resp", (), {"data": self.rows})()


class _FakeClient:
    def __init__(self) -> None:
        self.table_obj = _FakeTable()
        self.last_schema_name: str | None = None
        self.last_table_name: str | None = None

    def schema(self, name):
        self.last_schema_name = name
        return self

    def table(self, name):
        self.last_table_name = name
        return self.table_obj


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


def test_supabase_monitor_operation_repo_fails_loudly_when_monitor_operations_table_is_missing() -> None:
    client = _FakeClient()
    client.table_obj.error = RuntimeError("Could not find the table 'observability.monitor_operations' in the schema cache")
    repo = SupabaseMonitorOperationRepo(client=client)

    with pytest.raises(RuntimeError, match="observability\\.monitor_operations is missing") as exc_info:
        repo.list_for_target("sandbox", "sandbox-1")

    assert "schema cache" in str(exc_info.value)


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
