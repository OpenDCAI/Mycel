import pytest

from storage.providers.supabase.lease_repo import SupabaseLeaseRepo
from tests.fakes.supabase import FakeSupabaseClient


class _RejectSandboxInstancesClient(FakeSupabaseClient):
    def table(self, table_name: str):
        if table_name == "sandbox_instances":
            raise AssertionError("sandbox_instances table should not be accessed")
        return super().table(table_name)


def test_supabase_lease_repo_adopt_instance_fails_loudly_if_bootstrap_reload_missing():
    repo = SupabaseLeaseRepo(client=FakeSupabaseClient(tables={"sandbox_leases": [], "sandbox_instances": []}))
    rows = iter([None, None])

    repo.create = lambda **_kwargs: {  # type: ignore[method-assign]
        "lease_id": "lease-1",
        "provider_name": "test-provider",
    }
    repo.get = lambda _lease_id: next(rows)  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="failed to load lease after adopt_instance bootstrap"):
        repo.adopt_instance(
            lease_id="lease-1",
            provider_name="test-provider",
            instance_id="inst-123",
        )


def test_supabase_lease_repo_get_synthesizes_instance_from_lease_row_without_instances_table():
    tables = {
        "sandbox_leases": [
            {
                "lease_id": "lease-1",
                "provider_name": "local",
                "recipe_id": None,
                "workspace_key": None,
                "recipe_json": None,
                "current_instance_id": "inst-1",
                "instance_created_at": "2026-04-07T00:00:01+00:00",
                "desired_state": "running",
                "observed_state": "running",
                "version": 0,
                "observed_at": "2026-04-07T00:00:05+00:00",
                "last_error": None,
                "needs_refresh": 0,
                "refresh_hint_at": None,
                "status": "active",
                "created_at": "2026-04-07T00:00:00+00:00",
                "updated_at": "2026-04-07T00:00:05+00:00",
            }
        ]
    }
    repo = SupabaseLeaseRepo(client=_RejectSandboxInstancesClient(tables=tables))

    lease = repo.get("lease-1")

    assert lease is not None
    assert lease["_instance"] == {
        "instance_id": "inst-1",
        "lease_id": "lease-1",
        "provider_session_id": "inst-1",
        "status": "running",
        "created_at": "2026-04-07T00:00:01+00:00",
        "last_seen_at": "2026-04-07T00:00:05+00:00",
    }


class _FakeTable:
    def __init__(self) -> None:
        self.insert_payload = None
        self.selected_cols = None
        self.eq_calls: list[tuple[str, object]] = []
        self.rows = [
            {
                "lease_id": "lease-1",
                "provider_name": "local",
                "recipe_id": None,
                "workspace_key": None,
                "recipe_json": None,
                "current_instance_id": None,
                "instance_created_at": None,
                "desired_state": "running",
                "observed_state": "detached",
                "version": 0,
                "observed_at": "2026-04-07T00:00:00",
                "last_error": None,
                "needs_refresh": 0,
                "refresh_hint_at": None,
                "status": "active",
                "created_at": "2026-04-07T00:00:00",
                "updated_at": "2026-04-07T00:00:00",
            }
        ]

    def insert(self, payload):
        self.insert_payload = payload
        return self

    def select(self, cols):
        self.selected_cols = cols
        return self

    def eq(self, key, value):
        self.eq_calls.append((key, value))
        return self

    def execute(self):
        return type("Resp", (), {"data": self.rows})()


class _FakeClient:
    def __init__(self) -> None:
        self.tables = {
            "sandbox_leases": _FakeTable(),
            "sandbox_instances": _FakeTable(),
        }

    def table(self, name):
        return self.tables[name]


def test_supabase_lease_repo_create_persists_integer_refresh_flag():
    client = _FakeClient()
    repo = SupabaseLeaseRepo(client)

    repo.create("lease-1", "local")

    refresh_flag = client.tables["sandbox_leases"].insert_payload["needs_refresh"]
    assert refresh_flag == 0
    assert type(refresh_flag) is int


def test_supabase_lease_repo_create_persists_utc_timestamps():
    client = _FakeClient()
    repo = SupabaseLeaseRepo(client)

    repo.create("lease-1", "local")

    payload = client.tables["sandbox_leases"].insert_payload
    assert payload["created_at"].endswith("+00:00")
    assert payload["updated_at"].endswith("+00:00")
    assert payload["observed_at"].endswith("+00:00")


def test_supabase_lease_repo_create_does_not_write_legacy_volume_id():
    client = _FakeClient()
    repo = SupabaseLeaseRepo(client)

    repo.create("lease-1", "local")

    payload = client.tables["sandbox_leases"].insert_payload
    assert "volume_id" not in payload


def test_supabase_lease_repo_get_does_not_select_legacy_volume_id():
    client = _FakeClient()
    repo = SupabaseLeaseRepo(client)

    result = repo.get("lease-1")

    assert result is not None
    assert "volume_id" not in client.tables["sandbox_leases"].selected_cols


def test_supabase_lease_repo_adopt_instance_persists_integer_refresh_flag():
    tables = {
        "sandbox_leases": [
            {
                "lease_id": "lease-1",
                "provider_name": "local",
                "recipe_id": None,
                "workspace_key": None,
                "recipe_json": None,
                "current_instance_id": None,
                "instance_created_at": None,
                "desired_state": "running",
                "observed_state": "detached",
                "version": 0,
                "observed_at": "2026-04-07T00:00:00+00:00",
                "last_error": None,
                "needs_refresh": 0,
                "refresh_hint_at": None,
                "status": "active",
                "created_at": "2026-04-07T00:00:00+00:00",
                "updated_at": "2026-04-07T00:00:00+00:00",
            }
        ],
        "sandbox_instances": [],
    }
    repo = SupabaseLeaseRepo(client=FakeSupabaseClient(tables=tables))

    repo.adopt_instance(
        lease_id="lease-1",
        provider_name="local",
        instance_id="inst-1",
        status="running",
    )

    lease_row = tables["sandbox_leases"][0]
    assert lease_row["needs_refresh"] == 1
    assert type(lease_row["needs_refresh"]) is int


def test_supabase_lease_repo_adopt_instance_updates_lease_without_instances_table():
    tables = {
        "sandbox_leases": [
            {
                "lease_id": "lease-1",
                "provider_name": "local",
                "recipe_id": None,
                "workspace_key": None,
                "recipe_json": None,
                "current_instance_id": None,
                "instance_created_at": None,
                "desired_state": "running",
                "observed_state": "detached",
                "version": 0,
                "observed_at": "2026-04-07T00:00:00+00:00",
                "last_error": None,
                "needs_refresh": 0,
                "refresh_hint_at": None,
                "status": "active",
                "created_at": "2026-04-07T00:00:00+00:00",
                "updated_at": "2026-04-07T00:00:00+00:00",
            }
        ]
    }
    repo = SupabaseLeaseRepo(client=_RejectSandboxInstancesClient(tables=tables))

    updated = repo.adopt_instance(
        lease_id="lease-1",
        provider_name="local",
        instance_id="inst-1",
        status="running",
    )

    lease_row = tables["sandbox_leases"][0]
    assert lease_row["current_instance_id"] == "inst-1"
    assert lease_row["observed_state"] == "running"
    assert updated["_instance"]["instance_id"] == "inst-1"


def test_supabase_lease_repo_persist_metadata_updates_error_refresh_fields():
    tables = {
        "sandbox_leases": [
            {
                "lease_id": "lease-1",
                "provider_name": "local",
                "recipe_id": None,
                "workspace_key": None,
                "recipe_json": None,
                "current_instance_id": None,
                "instance_created_at": None,
                "desired_state": "running",
                "observed_state": "detached",
                "version": 0,
                "observed_at": "2026-04-07T00:00:00+00:00",
                "last_error": None,
                "needs_refresh": 0,
                "refresh_hint_at": None,
                "status": "active",
                "created_at": "2026-04-07T00:00:00+00:00",
                "updated_at": "2026-04-07T00:00:00+00:00",
            }
        ],
        "sandbox_instances": [],
    }
    repo = SupabaseLeaseRepo(client=FakeSupabaseClient(tables=tables))

    updated = repo.persist_metadata(
        lease_id="lease-1",
        recipe_id=None,
        recipe_json=None,
        desired_state="running",
        observed_state="unknown",
        version=3,
        observed_at="2026-04-07T00:00:05+00:00",
        last_error="provider boom",
        needs_refresh=True,
        refresh_hint_at="2026-04-07T00:00:06+00:00",
        status="recovering",
    )

    lease_row = tables["sandbox_leases"][0]
    assert updated["lease_id"] == "lease-1"
    assert lease_row["observed_state"] == "unknown"
    assert lease_row["version"] == 3
    assert lease_row["last_error"] == "provider boom"
    assert lease_row["needs_refresh"] == 1
    assert type(lease_row["needs_refresh"]) is int
    assert lease_row["refresh_hint_at"] == "2026-04-07T00:00:06+00:00"
    assert lease_row["status"] == "recovering"


def test_supabase_lease_repo_observe_status_detaches_instance_without_instances_table():
    tables = {
        "sandbox_leases": [
            {
                "lease_id": "lease-1",
                "provider_name": "local",
                "recipe_id": None,
                "workspace_key": None,
                "recipe_json": None,
                "current_instance_id": "inst-1",
                "instance_created_at": "2026-04-07T00:00:01+00:00",
                "desired_state": "running",
                "observed_state": "running",
                "version": 0,
                "observed_at": "2026-04-07T00:00:00+00:00",
                "last_error": "old error",
                "needs_refresh": 1,
                "refresh_hint_at": "2026-04-07T00:00:02+00:00",
                "status": "active",
                "created_at": "2026-04-07T00:00:00+00:00",
                "updated_at": "2026-04-07T00:00:00+00:00",
            }
        ],
    }
    repo = SupabaseLeaseRepo(client=_RejectSandboxInstancesClient(tables=tables))

    updated = repo.observe_status(
        lease_id="lease-1",
        status="detached",
        observed_at="2026-04-07T00:00:05+00:00",
    )

    lease_row = tables["sandbox_leases"][0]
    assert updated["lease_id"] == "lease-1"
    assert lease_row["current_instance_id"] is None
    assert lease_row["observed_state"] == "detached"
    assert lease_row["status"] == "expired"
    assert lease_row["last_error"] is None
    assert lease_row["needs_refresh"] == 0
    assert type(lease_row["needs_refresh"]) is int
    assert lease_row["version"] == 1
    assert updated["_instance"] is None


def test_supabase_lease_repo_delete_removes_lease_without_instances_table():
    tables = {
        "sandbox_leases": [
            {
                "lease_id": "lease-1",
                "provider_name": "local",
            }
        ]
    }
    repo = SupabaseLeaseRepo(client=_RejectSandboxInstancesClient(tables=tables))

    repo.delete("lease-1")

    assert tables["sandbox_leases"] == []
