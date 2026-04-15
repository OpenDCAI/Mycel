from storage.providers.supabase.resource_snapshot_repo import SupabaseResourceSnapshotRepo


class _FakeTable:
    def __init__(self) -> None:
        self.upsert_payload = None
        self.in_calls: list[tuple[str, list[str]]] = []
        self.max_in_values: int | None = None
        self.rows = [{"lease_id": "lease-1", "cpu_used": 1.0}]

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

    def table(self, _name):
        return self.table_obj


def test_supabase_resource_snapshot_repo_upserts_with_client() -> None:
    client = _FakeClient()
    repo = SupabaseResourceSnapshotRepo(client)

    repo.upsert_lease_resource_snapshot(
        lease_id="lease-1",
        provider_name="daytona",
        observed_state="running",
        probe_mode="runtime",
    )

    assert client.table_obj.upsert_payload is not None
    assert client.table_obj.upsert_payload["lease_id"] == "lease-1"
    assert client.table_obj.upsert_payload["provider_name"] == "daytona"


def test_supabase_resource_snapshot_repo_upserts_for_sandbox_with_legacy_bridge() -> None:
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
    assert client.table_obj.upsert_payload["lease_id"] == "lease-1"
    assert client.table_obj.upsert_payload["provider_name"] == "daytona"


def test_supabase_resource_snapshot_repo_lists_snapshots_by_lease_ids() -> None:
    client = _FakeClient()
    repo = SupabaseResourceSnapshotRepo(client)

    rows = repo.list_snapshots_by_lease_ids(["lease-1", "lease-2"])

    assert rows == {"lease-1": {"lease_id": "lease-1", "cpu_used": 1.0}}
    assert ("lease_id", ["lease-1", "lease-2"]) in client.table_obj.in_calls


def test_supabase_resource_snapshot_repo_lists_snapshots_by_sandbox_ids() -> None:
    client = _FakeClient()
    repo = SupabaseResourceSnapshotRepo(client)

    rows = repo.list_snapshots_by_sandbox_ids(
        [
            {"sandbox_id": "sandbox-1", "lease_id": "lease-1"},
            {"sandbox_id": "sandbox-2", "lease_id": "lease-2"},
        ]
    )

    assert rows == {"sandbox-1": {"lease_id": "lease-1", "cpu_used": 1.0}}
    assert ("lease_id", ["lease-1", "lease-2"]) in client.table_obj.in_calls


def test_supabase_resource_snapshot_repo_chunks_large_snapshot_lookup() -> None:
    client = _FakeClient()
    client.table_obj.max_in_values = 80
    repo = SupabaseResourceSnapshotRepo(client)

    rows = repo.list_snapshots_by_lease_ids([f"lease-{index}" for index in range(175)])

    assert rows == {"lease-1": {"lease_id": "lease-1", "cpu_used": 1.0}}
    assert [len(values) for _, values in client.table_obj.in_calls] == [80, 80, 15]
