from storage.providers.supabase.resource_snapshot_repo import SupabaseResourceSnapshotRepo


class _FakeTable:
    def __init__(self) -> None:
        self.upsert_payload = None
        self.in_calls: list[tuple[str, list[str]]] = []
        self.rows = [{"lease_id": "lease-1", "cpu_used": 1.0}]

    def upsert(self, payload):
        self.upsert_payload = payload
        return self

    def select(self, _cols):
        return self

    def in_(self, key, values):
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


def test_supabase_resource_snapshot_repo_lists_snapshots_by_lease_ids() -> None:
    client = _FakeClient()
    repo = SupabaseResourceSnapshotRepo(client)

    rows = repo.list_snapshots_by_lease_ids(["lease-1", "lease-2"])

    assert rows == {"lease-1": {"lease_id": "lease-1", "cpu_used": 1.0}}
    assert ("lease_id", ["lease-1", "lease-2"]) in client.table_obj.in_calls
