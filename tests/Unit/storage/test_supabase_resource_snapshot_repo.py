import storage.providers.supabase as supabase_provider
from storage.contracts import ResourceSnapshotRepo
from storage.providers.supabase.resource_snapshot_repo import SupabaseResourceSnapshotRepo


class _FakeTable:
    def __init__(self) -> None:
        self.upsert_payload = None
        self.in_calls: list[tuple[str, list[str]]] = []
        self.max_in_values: int | None = None
        self.rows = [{"sandbox_id": "sandbox-1", "cpu_used": 1.0}]

    def upsert(self, payload):
        self.upsert_payload = payload
        return self

    def select(self, _cols):
        return self

    def in_(self, key, values):
        if self.max_in_values is not None:
            assert len(values) <= self.max_in_values
        self.in_calls.append((key, list(values)))
        return self

    def execute(self):
        return type("Resp", (), {"data": self.rows})()


class _FakeClient:
    def __init__(self) -> None:
        self.table_obj = _FakeTable()
        self.last_table_name: str | None = None

    def table(self, name):
        self.last_table_name = name
        return self.table_obj


def test_supabase_resource_snapshot_repo_upserts_for_sandbox_without_lease_shaped_row_key() -> None:
    client = _FakeClient()
    repo = SupabaseResourceSnapshotRepo(client)

    repo.upsert_resource_snapshot_for_sandbox(
        sandbox_id="sandbox-1",
        legacy_lease_id="lease-1",
        provider_name="daytona",
        observed_state="running",
        probe_mode="runtime",
    )

    assert client.table_obj.upsert_payload is not None
    assert client.last_table_name == "sandbox_resource_snapshots"
    assert client.table_obj.upsert_payload["sandbox_id"] == "sandbox-1"
    assert "lease_id" not in client.table_obj.upsert_payload
    assert client.table_obj.upsert_payload["provider_name"] == "daytona"


def test_supabase_resource_snapshot_repo_lists_snapshots_by_sandbox_ids() -> None:
    client = _FakeClient()
    repo = SupabaseResourceSnapshotRepo(client)

    rows = repo.list_snapshots_by_sandbox_ids(
        [
            {"sandbox_id": "sandbox-1", "lease_id": "lease-1"},
            {"sandbox_id": "sandbox-2", "lease_id": "lease-2"},
        ]
    )

    assert rows == {"sandbox-1": {"sandbox_id": "sandbox-1", "cpu_used": 1.0}}
    assert client.last_table_name == "sandbox_resource_snapshots"
    assert ("sandbox_id", ["sandbox-1", "sandbox-2"]) in client.table_obj.in_calls


def test_supabase_resource_snapshot_repo_chunks_large_snapshot_lookup() -> None:
    client = _FakeClient()
    client.table_obj.max_in_values = 80
    repo = SupabaseResourceSnapshotRepo(client)

    rows = repo.list_snapshots_by_sandbox_ids([{"sandbox_id": f"sandbox-{index}", "lease_id": f"lease-{index}"} for index in range(175)])

    assert rows == {"sandbox-1": {"sandbox_id": "sandbox-1", "cpu_used": 1.0}}
    assert [len(values) for _, values in client.table_obj.in_calls] == [80, 80, 15]


def test_resource_snapshot_repo_protocol_no_longer_declares_lease_shaped_methods() -> None:
    assert "upsert_lease_resource_snapshot" not in ResourceSnapshotRepo.__dict__
    assert "list_snapshots_by_lease_ids" not in ResourceSnapshotRepo.__dict__


def test_supabase_provider_package_no_longer_exports_lease_shaped_snapshot_helpers() -> None:
    assert not hasattr(supabase_provider, "upsert_lease_resource_snapshot")
    assert not hasattr(supabase_provider, "list_snapshots_by_lease_ids")
